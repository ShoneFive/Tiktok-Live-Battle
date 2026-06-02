import tkinter as tk
import socket
import random
import os

AVATARES_DIR = "avatares"
UDP_IP = "127.0.0.1"
UDP_PORT = 5005

sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

def enviar_comando(cmd_str):
    try:
        sock.sendto(cmd_str.encode('utf-8'), (UDP_IP, UDP_PORT))
    except Exception as e:
        print(f"Erro ao enviar comando: {e}")

def spawn_bot():
    nomes_ficticios = ["Carlos J.", "Mestre 99", "Shadow Ninja", "Gamer Pro", "Ana Clara", "Pedro FPS"]
    nome = random.choice(nomes_ficticios) + " " + str(random.randint(10, 99))
    
    avatar_path = ""
    if os.path.exists(AVATARES_DIR):
        arquivos = [f for f in os.listdir(AVATARES_DIR) if f.endswith(".png")]
        if arquivos:
            escolha = random.choice(arquivos)
            # Converter para caminho absoluto para o Pygame conseguir carregar
            avatar_path = os.path.abspath(os.path.join(AVATARES_DIR, escolha))
    
    cmd = f"spawn|{nome}|{avatar_path}"
    enviar_comando(cmd)
    
    listbox_bots.insert(tk.END, nome)
    
def dar_presente():
    nome = entry_nome.get().strip()
    if not nome: return
    # Formato: gift|nome|1000.0
    cmd = f"gift|{nome}|1000.0"
    enviar_comando(cmd)

def dar_like():
    nome = entry_nome.get().strip()
    if not nome: return
    # Formato: like|nome
    cmd = f"like|{nome}"
    enviar_comando(cmd)

root = tk.Tk()
root.title("Dashboard de Controle - AntiGravity")
root.geometry("380x280")
root.configure(padx=20, pady=20)

tk.Label(root, text="Controles da Arena", font=("Arial", 16, "bold")).pack(pady=10)

btn_spawn = tk.Button(root, text="🤖 Spawnar Bot Aleatório (Anime)", command=spawn_bot, bg="#4CAF50", fg="white", font=("Arial", 12))
btn_spawn.pack(fill="x", pady=10)

frame_acoes = tk.Frame(root)
frame_acoes.pack(fill="x", pady=10)

tk.Label(frame_acoes, text="Nome do Alvo:").pack(side="left")
entry_nome = tk.Entry(frame_acoes, font=("Arial", 12))
entry_nome.pack(side="left", fill="x", expand=True, padx=5)

frame_btns = tk.Frame(root)
frame_btns.pack(fill="x", pady=10)

btn_gift = tk.Button(frame_btns, text="🎁 Presente (1000 HP)", command=dar_presente, bg="#FF9800", fg="white", font=("Arial", 10, "bold"))
btn_gift.pack(side="left", expand=True, fill="x", padx=5)

btn_like = tk.Button(frame_btns, text="❤️ Curar (Like)", command=dar_like, bg="#E91E63", fg="white", font=("Arial", 10, "bold"))
btn_like.pack(side="left", expand=True, fill="x", padx=5)

def selecionar_bot(event):
    selecionado = listbox_bots.curselection()
    if selecionado:
        nome = listbox_bots.get(selecionado[0])
        entry_nome.delete(0, tk.END)
        entry_nome.insert(0, nome)

tk.Label(root, text="Últimos Bots Spawnados (clique para selecionar):", font=("Arial", 10)).pack(anchor="w", pady=(10, 0))
listbox_bots = tk.Listbox(root, height=4, font=("Arial", 11))
listbox_bots.pack(fill="x", pady=5)
listbox_bots.bind('<<ListboxSelect>>', selecionar_bot)

root.geometry("380x420")
root.mainloop()
