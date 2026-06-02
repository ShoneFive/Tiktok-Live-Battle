import pyautogui
import keyboard
import time

# ==========================================
# CONFIGURAÇÃO
X = 1880       # Posição Horizontal (Eixo X)
Y = 995      # Posição Vertical (Eixo Y)
DELAY = 0.1   # Tempo de espera entre os cliques (em segundos)
# ==========================================

print("Rodando... Pressione 'F8' para ligar/pausar o clique. Segure 'ESC' para encerrar totalmente.")
rodando = False

while True:
    # Trava de segurança para fechar o script
    if keyboard.is_pressed('esc'):
        print("Script encerrado.")
        break

    # Gatilho de liga/desliga
    if keyboard.is_pressed('f8'):
        rodando = not rodando
        estado = "LIGADO - Clicando..." if rodando else "PAUSADO"
        print(f"Status alterado: {estado}")
        time.sleep(0.3) # Pequeno delay para a tecla não registrar duas vezes

    # Execução do clique
    if rodando:
        pyautogui.click(x=X, y=Y)
        time.sleep(DELAY)