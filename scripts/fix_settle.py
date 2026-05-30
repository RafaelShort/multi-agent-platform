import pathlib

path = pathlib.Path("core/messaging/message_bus.py")
content = path.read_text(encoding="utf-8")

old = '''        if assigned:
            logger.info(f"📥 Consumer pronto | topicos: {all_topics}")
        else:
            logger.warning(f"⚠️ Timeout aguardando particoes: {all_topics}")'''

new = '''        if assigned:
            # Settle delay: deixa o consumer estabelecer position nas particoes
            # antes de retornar (evita race com publish imediato apos rebalance)
            await asyncio.sleep(0.5)
            logger.info(f"📥 Consumer pronto | topicos: {all_topics}")
        else:
            logger.warning(f"⚠️ Timeout aguardando particoes: {all_topics}")'''

if old in content:
    content = content.replace(old, new)
    path.write_text(content, encoding="utf-8")
    print("✅ Settle delay aplicado")
else:
    print("❌ Trecho nao encontrado")

# Verificar
content2 = path.read_text(encoding="utf-8")
if "Settle delay" in content2:
    print("✅ Verificado: settle delay no codigo")
