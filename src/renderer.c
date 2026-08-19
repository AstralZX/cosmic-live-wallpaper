#include <gtk4-layer-shell.h>
#include <gtk/gtk.h>
#include <gst/gst.h>
#include <gst/video/video.h>
#include <gst/app/gstappsink.h>
#include <stdio.h>
#include <string.h>

typedef struct {
    GstElement *pipeline;
    guint bus_watch_id;
    GtkWidget *window;
    GtkWidget *picture;
    GMutex lock;
    char *uri;
    int tex_w, tex_h;
    GdkTexture *texture;
    GdkPixbuf *pixbuf;
} AppData;

static GstFlowReturn on_new_sample(GstAppSink *appsink, gpointer user_data) {
    AppData *app = (AppData *)user_data;
    GstSample *sample = gst_app_sink_pull_sample(appsink);
    if (!sample) return GST_FLOW_ERROR;
    GstCaps *caps = gst_sample_get_caps(sample);
    GstStructure *s = gst_caps_get_structure(caps, 0);
    int w = 0, h = 0;
    gst_structure_get_int(s, "width", &w);
    gst_structure_get_int(s, "height", &h);
    GstBuffer *buffer = gst_sample_get_buffer(sample);
    GstMapInfo map;
    if (!gst_buffer_map(buffer, &map, GST_MAP_READ)) {
        gst_sample_unref(sample);
        return GST_FLOW_ERROR;
    }
    int copy_rowsize = w * 4;
    g_mutex_lock(&app->lock);
    if (!app->pixbuf || app->tex_w != w || app->tex_h != h) {
        if (app->pixbuf) g_object_unref(app->pixbuf);
        app->pixbuf = gdk_pixbuf_new(GDK_COLORSPACE_RGB, TRUE, 8, w, h);
        app->tex_w = w;
        app->tex_h = h;
    }
    guint8 *dst = gdk_pixbuf_get_pixels(app->pixbuf);
    int dst_rowstride = gdk_pixbuf_get_rowstride(app->pixbuf);
    for (int y = 0; y < h; y++) {
        memcpy(dst + y * dst_rowstride, map.data + y * copy_rowsize, copy_rowsize);
    }
    if (app->texture) g_object_unref(app->texture);
    app->texture = gdk_texture_new_for_pixbuf(app->pixbuf);
    gtk_picture_set_paintable(GTK_PICTURE(app->picture), GDK_PAINTABLE(app->texture));
    g_mutex_unlock(&app->lock);
    gst_buffer_unmap(buffer, &map);
    gst_sample_unref(sample);
    return GST_FLOW_OK;
}

static void pad_added_cb(GstElement *src, GstPad *new_pad, gpointer user_data) {
    GstElement *convert = GST_ELEMENT(user_data);
    GstPad *sink_pad = gst_element_get_static_pad(convert, "sink");
    (void)src;
    if (gst_pad_is_linked(sink_pad)) { gst_object_unref(sink_pad); return; }
    GstCaps *caps = gst_pad_get_current_caps(new_pad);
    if (!caps) caps = gst_pad_query_caps(new_pad, NULL);
    GstStructure *st = gst_caps_get_structure(caps, 0);
    const gchar *type = gst_structure_get_name(st);
    if (g_str_has_prefix(type, "video/")) {
        if (GST_PAD_LINK_FAILED(gst_pad_link(new_pad, sink_pad)))
            fprintf(stderr, "Failed to link video pad\n");
    }
    gst_caps_unref(caps);
    gst_object_unref(sink_pad);
}

static gboolean bus_call(GstBus *bus, GstMessage *msg, gpointer user_data);

static void teardown_pipeline(AppData *data) {
    if (data->bus_watch_id) {
        g_source_remove(data->bus_watch_id);
        data->bus_watch_id = 0;
    }
    if (data->pipeline) {
        gst_element_set_state(data->pipeline, GST_STATE_NULL);
        gst_object_unref(data->pipeline);
        data->pipeline = NULL;
    }
}

static GstElement *build_pipeline(AppData *data) {
    GstElement *pipeline = gst_pipeline_new("wp");
    GstElement *source = gst_element_factory_make("uridecodebin", "src");
    GstElement *convert = gst_element_factory_make("videoconvert", "conv");
    GstElement *scale = gst_element_factory_make("videoscale", "scale");
    GstElement *sink = gst_element_factory_make("appsink", "sink");
    if (!pipeline || !source || !convert || !scale || !sink) {
        fprintf(stderr, "Error: failed to create elements\n");
        return NULL;
    }
    g_object_set(source, "uri", data->uri, NULL);
    g_object_set(sink, "emit-signals", TRUE, "max-buffers", 1, "drop", TRUE, "wait-on-eos", FALSE, NULL);
    GstCaps *caps = gst_caps_new_simple("video/x-raw", "format", G_TYPE_STRING, "RGBA", NULL);
    g_object_set(sink, "caps", caps, NULL);
    gst_caps_unref(caps);
    GstAppSinkCallbacks cb = { .new_sample = on_new_sample };
    gst_app_sink_set_callbacks(GST_APP_SINK(sink), &cb, data, NULL);
    gst_bin_add_many(GST_BIN(pipeline), source, convert, scale, sink, NULL);
    g_signal_connect(source, "pad-added", G_CALLBACK(pad_added_cb), convert);
    if (!gst_element_link_many(convert, scale, sink, NULL)) {
        fprintf(stderr, "Error: failed to link\n");
        gst_object_unref(pipeline);
        return NULL;
    }
    return pipeline;
}

static gboolean bus_call(GstBus *bus, GstMessage *msg, gpointer user_data) {
    AppData *data = (AppData *)user_data;
    (void)bus;
    switch (GST_MESSAGE_TYPE(msg)) {
    case GST_MESSAGE_ERROR: {
        GError *err = NULL;
        gchar *debug = NULL;
        gst_message_parse_error(msg, &err, &debug);
        fprintf(stderr, "GStreamer error: %s\n", err->message ? err->message : "unknown");
        if (debug) fprintf(stderr, "Debug: %s\n", debug);
        g_error_free(err);
        g_free(debug);
        break;
    }
    case GST_MESSAGE_EOS:
        fprintf(stderr, "Looping\n");
        teardown_pipeline(data);
        data->pipeline = build_pipeline(data);
        if (data->pipeline) {
            GstBus *new_bus = gst_element_get_bus(data->pipeline);
            data->bus_watch_id = gst_bus_add_watch(new_bus, bus_call, data);
            gst_object_unref(new_bus);
            gst_element_set_state(data->pipeline, GST_STATE_PLAYING);
        }
        break;
    default:
        break;
    }
    return TRUE;
}

static void cleanup(AppData *data) {
    teardown_pipeline(data);
    g_mutex_lock(&data->lock);
    if (data->texture) g_object_unref(data->texture);
    if (data->pixbuf) g_object_unref(data->pixbuf);
    g_mutex_unlock(&data->lock);
    g_mutex_clear(&data->lock);
    g_free(data->uri);
}

static void activate(GtkApplication *app, gpointer user_data) {
    AppData *data = (AppData *)user_data;
    data->window = gtk_application_window_new(app);
    gtk_window_set_decorated(GTK_WINDOW(data->window), FALSE);
    gtk_layer_init_for_window(GTK_WINDOW(data->window));
    gtk_layer_set_layer(GTK_WINDOW(data->window), GTK_LAYER_SHELL_LAYER_BACKGROUND);
    gtk_layer_set_namespace(GTK_WINDOW(data->window), "cosmic-live-wallpaper");
    gtk_layer_set_anchor(GTK_WINDOW(data->window), GTK_LAYER_SHELL_EDGE_TOP, TRUE);
    gtk_layer_set_anchor(GTK_WINDOW(data->window), GTK_LAYER_SHELL_EDGE_BOTTOM, TRUE);
    gtk_layer_set_anchor(GTK_WINDOW(data->window), GTK_LAYER_SHELL_EDGE_LEFT, TRUE);
    gtk_layer_set_anchor(GTK_WINDOW(data->window), GTK_LAYER_SHELL_EDGE_RIGHT, TRUE);
    gtk_layer_set_exclusive_zone(GTK_WINDOW(data->window), -1);
    gtk_layer_set_keyboard_mode(GTK_WINDOW(data->window), GTK_LAYER_SHELL_KEYBOARD_MODE_NONE);
    const char *target_output = g_object_get_data(G_OBJECT(app), "target-output");
    if (target_output) {
        GdkDisplay *display = gtk_widget_get_display(GTK_WIDGET(data->window));
        GListModel *monitors = gdk_display_get_monitors(display);
        guint n = g_list_model_get_n_items(monitors);
        for (guint i = 0; i < n; i++) {
            GdkMonitor *mon = GDK_MONITOR(g_list_model_get_item(monitors, i));
            const char *model = gdk_monitor_get_model(mon);
            if (model && strcmp(model, target_output) == 0) {
                gtk_layer_set_monitor(GTK_WINDOW(data->window), mon);
                fprintf(stderr, "Monitor: %s\n", model);
                g_object_unref(mon);
                break;
            }
            g_object_unref(mon);
        }
    }
    data->picture = gtk_picture_new();
    gtk_widget_set_hexpand(data->picture, TRUE);
    gtk_widget_set_vexpand(data->picture, TRUE);
    gtk_picture_set_content_fit(GTK_PICTURE(data->picture), GTK_CONTENT_FIT_CONTAIN);
    gtk_window_set_child(GTK_WINDOW(data->window), data->picture);
    data->pipeline = build_pipeline(data);
    if (data->pipeline) {
        GstBus *bus = gst_element_get_bus(data->pipeline);
        data->bus_watch_id = gst_bus_add_watch(bus, bus_call, data);
        gst_object_unref(bus);
    }
    gtk_widget_set_visible(data->window, TRUE);
    gst_element_set_state(data->pipeline, GST_STATE_PLAYING);
    fprintf(stderr, "Playing\n");
}

int main(int argc, char *argv[]) {
    if (argc < 2) {
        fprintf(stderr, "Usage: %s <video-file> [output]\n", argv[0]);
        return 1;
    }
    const char *video_path = argv[1];
    const char *target_output = (argc > 2) ? argv[2] : NULL;
    GFile *file = g_file_new_for_path(video_path);
    if (!g_file_query_exists(file, NULL)) {
        fprintf(stderr, "Error: '%s' not found\n", video_path);
        g_object_unref(file);
        return 1;
    }
    g_object_unref(file);
    gst_init(NULL, NULL);
    gtk_init();
    AppData data = {0};
    g_mutex_init(&data.lock);
    data.uri = g_strdup_printf("file://%s", video_path);
    GtkApplication *app = gtk_application_new("com.cosmic.LiveWallpaper", G_APPLICATION_DEFAULT_FLAGS);
    if (target_output)
        g_object_set_data_full(G_OBJECT(app), "target-output", g_strdup(target_output), g_free);
    g_signal_connect(app, "activate", G_CALLBACK(activate), &data);
    int status = g_application_run(G_APPLICATION(app), 0, NULL);
    cleanup(&data);
    g_object_unref(app);
    return status;
}
