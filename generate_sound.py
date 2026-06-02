import wave
import struct
import random
import math

def generate_hit_sound():
    sample_rate = 44100
    duration = 0.15  # 150ms
    num_samples = int(sample_rate * duration)
    
    with wave.open("hit.wav", "w") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2) # 16-bit
        wav_file.setframerate(sample_rate)
        
        for i in range(num_samples):
            # Envelope (decay rápido para som de impacto)
            envelope = math.exp(-i / (num_samples * 0.3))
            
            # Mix de ruído com onda quadrada para parecer metal 8-bits batendo
            noise = random.uniform(-1.0, 1.0)
            
            # Frequência decrescente (pitch drop) típico de impacto
            freq = 1200.0 - (800.0 * (i / num_samples))
            square = 1.0 if (i * freq / sample_rate) % 1.0 > 0.5 else -1.0
            
            sample = (noise * 0.4 + square * 0.6) * envelope * 12000
            
            data = struct.pack('<h', int(sample))
            wav_file.writeframesraw(data)

if __name__ == "__main__":
    generate_hit_sound()
    print("hit.wav generated.")
