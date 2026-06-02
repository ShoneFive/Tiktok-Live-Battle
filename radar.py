import pyautogui
import keyboard
import time

print("Movimente o mouse para encontrar as coordenadas...")
print("Pressione a tecla 'ESPAÇO' para capturar e travar o alvo.\n")

while True:
    # Pega a posição atual do mouse
    x, y = pyautogui.position()
    
    # Imprime os valores na mesma linha do terminal (fica limpo e visual)
    print(f"\rPosição atual -> X: {x:4} | Y: {y:4}  (Aperte ESPAÇO para travar)", end="")
    
    if keyboard.is_pressed('space'):
        print("\n\n✅ ALVO TRAVADO!")
        print(f"Vá no seu script principal e substitua por:\n")
        print(f"X = {x}")
        print(f"Y = {y}")
        break
        
    time.sleep(0.1)