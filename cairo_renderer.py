import sys
import ctypes
from ctypes import c_void_p, py_object, c_char_p, c_int, CDLL
import cairo
import sdl2.ext

# see pycairo.h
class CAPI(ctypes.Structure):
    _fields_ = [
        ("Context_Type", py_object),
        ("Context_FromContext", ctypes.PYFUNCTYPE(py_object, c_void_p, py_object, py_object)),
        ("dummy", ctypes.c_void_p*27),
        ("Surface_FromSurface", ctypes.PYFUNCTYPE(py_object, c_void_p, py_object))
    ]

def get_capi():
    if sys.version_info[0] == 2:
        PyCObject_AsVoidPtr = ctypes.PYFUNCTYPE(c_void_p, py_object)(
            ('PyCObject_AsVoidPtr', ctypes.pythonapi))
        ptr = PyCObject_AsVoidPtr(cairo.CAPI)
    else:
        PyCapsule_GetPointer = ctypes.PYFUNCTYPE(c_void_p, py_object, c_char_p)(
            ('PyCapsule_GetPointer', ctypes.pythonapi))
        ptr = PyCapsule_GetPointer(cairo.CAPI, b"cairo.CAPI")

    ptr = ctypes.cast(ptr, ctypes.POINTER(CAPI))
    return ptr.contents

lib = CDLL('libcairo.so.2')
xlib_surface_create = lib.cairo_xlib_surface_create
xlib_surface_create.restype = c_void_p
xlib_surface_create.argtypes = [
  c_void_p, # display,
  c_void_p, # drawable,
  c_void_p, # visual,
  c_int, # width
  c_int, # height
  ]

x11_helper = ctypes.CDLL('./x11_helper.so')
get_default_visual = x11_helper.get_default_visual
get_default_visual.restype = ctypes.c_void_p
get_default_visual.argtypes = [ ctypes.c_void_p ]

create_pixmap = x11_helper.create_pixmap
create_pixmap.restype = ctypes.c_void_p
create_pixmap.argtypes = [ ctypes.c_void_p, ctypes.c_void_p, ctypes.c_int, ctypes.c_int ]

copy_pixmap = x11_helper.copy_pixmap
copy_pixmap.restype = None
copy_pixmap.argtypes = [ ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_int, ctypes.c_int ]

class Renderer:
    def __init__(self, widget):
        self.widget = widget

        info = sdl2.syswm.SDL_SysWMinfo()
        info.version.major = 2
        assert sdl2.syswm.SDL_GetWindowWMInfo(widget.window.window, info)
        self.x11_display = info.info.x11.display
        self.x11_window = info.info.x11.window

        self.pixmap = create_pixmap(self.x11_display, self.x11_window, widget.width, widget.height)
        self.raw_surface = xlib_surface_create(
            self.x11_display,
            self.pixmap,
            get_default_visual(self.x11_display),
            widget.width,
            widget.height)
        self.surface = get_capi().Surface_FromSurface(
            self.raw_surface, cairo.XlibSurface)

    def flip(self):
        self.surface.flush()
        copy_pixmap(self.x11_display,
                    self.pixmap,
                    self.x11_window,
                    self.widget.width,
                    self.widget.height)

    # This code may leak because we do not release
    # the pixmap or xlib surface.
    def close(self):
        self.surface.finish()
