import sys
from loguru import logger
from core.config import settings


def setup_logger():
    """Configura o logger centralizado da plataforma."""
    
    # Remove o handler padrão
    logger.remove()

    # Console
    logger.add(
        sys.stdout,
        level=settings.LOG_LEVEL,
        format=(
            "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
            "<level>{level: <8}</level> | "
            "<cyan>{name}</cyan>:<cyan>{line}</cyan> | "
            "<level>{message}</level>"
        ),
        colorize=True,
    )

    # Arquivo
    logger.add(
        "logs/platform_{time:YYYY-MM-DD}.log",
        level="DEBUG",
        rotation="00:00",
        retention="7 days",
        encoding="utf-8",
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{line} | {message}",
    )

    logger.info(f"Logger iniciado — Nível: {settings.LOG_LEVEL}")
    return logger


# Logger pronto para importar
app_logger = setup_logger()
