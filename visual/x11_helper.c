// gcc -shared -o x11_helper.so x11_helper.c -lX11
#include <X11/Xlib.h>

Visual* get_default_visual(Display* dpy) {
    return DefaultVisual(dpy, DefaultScreen(dpy));
}

Pixmap create_pixmap(Display* dpy, Window window, int width, int height) {
    return XCreatePixmap(dpy, window, width, height, DefaultDepth(dpy, DefaultScreen(dpy)));
}

void copy_pixmap(Display* dpy, Pixmap pixmap, Window window, int width, int height) {
    XCopyArea(dpy, pixmap, window, DefaultGC(dpy, DefaultScreen(dpy)), 0, 0, width, height, 0, 0);
    XSync(dpy, False);
}
