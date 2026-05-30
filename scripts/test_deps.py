import pymongo
import motor
from packaging.version import Version

print(f"PyMongo: {pymongo.__version__}")

# motor usa _version ao inves de __version__
motor_version = motor._version.version
print(f"Motor:   {motor_version}")

v = Version(pymongo.__version__)
ok = Version("4.9") <= v < Version("4.10")

if ok:
    print("Compatibilidade motor x pymongo: OK")
else:
    print("Compatibilidade motor x pymongo: INCOMPATIVEL")
