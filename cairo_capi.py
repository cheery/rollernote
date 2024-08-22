import sys
import ctypes
from ctypes import c_void_p, py_object, c_char_p, c_int, CDLL
import cairo

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


