import ctypes
import numpy
import sdl2
import wave

class SDLDevice:
    def __init__(self, transport, left, right):
        self.transport = transport
        self.audio_loop_c = sdl2.SDL_AudioCallback(self._audio_loop)
        wanted = sdl2.SDL_AudioSpec(44100, sdl2.AUDIO_F32, 2, transport.engine.sample_count)
        wanted.callback = self.audio_loop_c
        wanted.userdata = None

        self.audio = sdl2.SDL_OpenAudio(ctypes.byref(wanted), None)
        self.channels = [left, right]
        sdl2.SDL_PauseAudio(0)

    def lock(self):
        sdl2.SDL_LockAudio()

    def unlock(self):
        sdl2.SDL_UnlockAudio()

    def _audio_loop(self, _, stream, length):
        self.transport.run()
        data = numpy.dstack(self.channels).flatten()
        ctypes.memmove(stream, data.ctypes.data, min(self.transport.engine.sample_count*8, length))

    def close(self):
        sdl2.SDL_PauseAudio(1)

class WavDevice:
    def __init__(self, filename, transport, *channels):
        self.transport = transport
        self.channels = channels
        fd = wave.open(filename, 'w')
        fd.setnchannels(len(channels))
        fd.setsampwidth(2) # 16-bit
        fd.setframerate(transport.engine.sample_rate)
        self.fd = fd

    def write_frame(self):
        self.transport.run()
        data = numpy.dstack(self.channels).flatten()
        data = (data * 32767).astype(numpy.int16) # To 16-bit PCM format
        self.fd.writeframes(data.tobytes())

    def close(self):
        self.fd.close()
