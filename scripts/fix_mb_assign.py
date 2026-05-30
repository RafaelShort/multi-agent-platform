import pathlib

path = pathlib.Path("core/messaging/message_bus.py")
content = path.read_text(encoding="utf-8")

# Reverter para latest 
content = content.replace(
    '"auto.offset.reset":  "earliest"',
    '"auto.offset.reset":  "latest"'
)

# on_assign aguarda TODOS os topicos
old_assign = '''        assigned_event = threading.Event()

        def on_assign(consumer, partitions):
            if partitions:
                assigned_event.set()'''

new_assign = '''        assigned_event = threading.Event()
        assigned_set   = set()

        def on_assign(consumer, partitions):
            for p in partitions:
                assigned_set.add(p.topic)
            # Sinalizar apenas quando TODOS os topicos tiverem particoes
            if all(t in assigned_set for t in all_topics):
                assigned_event.set()'''

if old_assign in content:
    content = content.replace(old_assign, new_assign)
    print("✅ Fix on_assign aplicado")
else:
    print("❌ on_assign nao encontrado - verificar manualmente")
    for i, l in enumerate(content.splitlines(), 1):
        if "on_assign" in l:
            print(f"  L{i}: {l.rstrip()}")

path.write_text(content, encoding="utf-8")

checks = [
    ('"auto.offset.reset":  "latest"', "auto.offset.reset = latest"),
    ("assigned_set", "assigned_set criado"),
    ("assigned_set.add(p.topic)", "assigned_set populado"),
    ("all(t in assigned_set for t in all_topics)", "verifica todos os topicos"),
]
print()
for pattern, label in checks:
    ok = "✅" if pattern in content else "❌"
    print(f"{ok} {label}")
