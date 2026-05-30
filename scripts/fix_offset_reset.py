import pathlib

path = pathlib.Path("core/messaging/message_bus.py")
content = path.read_text(encoding="utf-8")

old = '"auto.offset.reset":  "latest",'
new = '"auto.offset.reset":  "earliest",'

if old in content:
    content = content.replace(old, new)
    path.write_text(content, encoding="utf-8")
    print("✅ Fix aplicado: auto.offset.reset = earliest")
    # Verificar
    line = [l.strip() for l in content.splitlines() if "auto.offset.reset" in l]
    print(f"   Linha atual: {line}")
else:
    print("❌ Trecho nao encontrado")
    for i, l in enumerate(content.splitlines(), 1):
        if "offset.reset" in l:
            print(f"   Linha {i}: {l.strip()}")
