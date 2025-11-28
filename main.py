import os
from datetime import datetime
from typing import Literal, Dict, Optional

import requests
from fastapi import FastAPI
from pydantic import BaseModel

# ==========================
# CONFIG ESP32 (local vs Render)
# ==========================
# - LOCAL (en tu casa, backend corriendo en tu PC y ESP32 en la misma red):
#     set FORWARD_TO_ESP32=true
#     set ESP32_BASE_URL=http://192.168.1.50   (o la IP del ESP)
#
# - RENDER (backend en la nube):
#     NO pongas FORWARD_TO_ESP32 o déjala en false
#     (Render no puede ver la red local de tu casa).
#

ESP32_BASE_URL = os.getenv("ESP32_BASE_URL", "http://192.168.1.50")
FORWARD_TO_ESP32 = os.getenv("FORWARD_TO_ESP32", "false").lower() == "true"


def send_command_to_esp(path: str) -> None:
    """
    Envía el comando al ESP32 (por ejemplo /principal/open)
    si FORWARD_TO_ESP32=True. En Render normalmente estará en False.
    """
    if not FORWARD_TO_ESP32:
        return

    try:
        url = f"{ESP32_BASE_URL}{path}"
        print(f"[INFO] Enviando comando al ESP32: {url}")
        requests.get(url, timeout=3)
    except Exception as e:
        print(f"[WARN] No se pudo contactar al ESP32 en {path}: {e}")


# ==========================
# MODELOS DE ESTADO
# ==========================

class DoorState(BaseModel):
    name: str
    is_open: bool
    last_update: datetime


class LightState(BaseModel):
    room: Literal["cocina", "sala", "dorm"]
    is_on: bool
    last_update: datetime


class PirState(BaseModel):
    active: bool
    last_update: datetime


class UltraState(BaseModel):
    active: bool
    last_update: datetime
    last_distance_cm: Optional[float] = None


class DhtState(BaseModel):
    temperature: Optional[float] = None
    humidity: Optional[float] = None
    last_update: Optional[datetime] = None


class HouseState(BaseModel):
    doors: Dict[str, DoorState]
    lights: Dict[str, LightState]
    pir: PirState
    ultra: UltraState
    dht: DhtState
    modo_seguro: bool


# ==========================
# ESTADO EN MEMORIA
# ==========================

now = datetime.utcnow  # función helper para timestamps

state = HouseState(
    doors={
        "principal": DoorState(
            name="principal",
            is_open=False,
            last_update=now()
        ),
        "garage": DoorState(
            name="garage",
            is_open=False,
            last_update=now()
        ),
    },
    lights={
        "cocina": LightState(
            room="cocina",
            is_on=False,
            last_update=now()
        ),
        "sala": LightState(
            room="sala",
            is_on=False,
            last_update=now()
        ),
        "dorm": LightState(
            room="dorm",
            is_on=False,
            last_update=now()
        ),
    },
    pir=PirState(
        active=False,
        last_update=now()
    ),
    ultra=UltraState(
        active=False,
        last_update=now(),
        last_distance_cm=None
    ),
    dht=DhtState(
        temperature=None,
        humidity=None,
        last_update=None
    ),
    modo_seguro=False,
)

app = FastAPI(
    title="Casa IoT Backend",
    version="1.0.0",
    description="API para controlar y monitorear la Casa IoT (puertas, luces, sensores, etc.)",
)


# ==========================
# ENDPOINT GENERAL DE ESTADO
# ==========================

@app.get("/status", response_model=HouseState)
def get_status():
    """
    Devuelve el estado completo de la casa:
    puertas, luces, PIR, ultrasonido, DHT y modo seguro.
    """
    return state


# ==========================
# PUERTA PRINCIPAL
# ==========================

@app.api_route("/principal/open", methods=["GET", "POST"])
def principal_open():
    state.doors["principal"].is_open = True
    state.doors["principal"].last_update = now()
    state.modo_seguro = False  # si abres algo, ya no estás en modo seguro
    send_command_to_esp("/principal/open")
    return {
        "message": "Puerta principal abierta",
        "door": state.doors["principal"],
    }


@app.api_route("/principal/close", methods=["GET", "POST"])
def principal_close():
    state.doors["principal"].is_open = False
    state.doors["principal"].last_update = now()
    send_command_to_esp("/principal/close")
    return {
        "message": "Puerta principal cerrada",
        "door": state.doors["principal"],
    }


# ==========================
# PUERTA GARAGE
# ==========================

@app.api_route("/garage/open", methods=["GET", "POST"])
def garage_open():
    state.doors["garage"].is_open = True
    state.doors["garage"].last_update = now()
    state.modo_seguro = False
    send_command_to_esp("/garage/open")
    return {
        "message": "Puerta garage abierta",
        "door": state.doors["garage"],
    }


@app.api_route("/garage/close", methods=["GET", "POST"])
def garage_close():
    state.doors["garage"].is_open = False
    state.doors["garage"].last_update = now()
    send_command_to_esp("/garage/close")
    return {
        "message": "Puerta garage cerrada",
        "door": state.doors["garage"],
    }


# ==========================
# ULTRASONIDO
# ==========================

@app.api_route("/ultra/on", methods=["GET", "POST"])
def ultra_on():
    state.ultra.active = True
    state.ultra.last_update = now()
    send_command_to_esp("/ultra/on")
    return {
        "message": "Ultrasonido activado",
        "ultra": state.ultra,
    }


@app.api_route("/ultra/off", methods=["GET", "POST"])
def ultra_off():
    state.ultra.active = False
    state.ultra.last_update = now()
    send_command_to_esp("/ultra/off")
    return {
        "message": "Ultrasonido desactivado",
        "ultra": state.ultra,
    }


class UltraDistanceUpdate(BaseModel):
    distance_cm: float


@app.post("/ultra/distance")
def ultra_update_distance(data: UltraDistanceUpdate):
    """
    Endpoint para que el ESP32 envíe la última distancia medida.
    """
    state.ultra.last_distance_cm = data.distance_cm
    state.ultra.last_update = now()
    return {
        "message": "Distancia actualizada",
        "ultra": state.ultra,
    }


# ==========================
# LUCES
# ==========================

@app.api_route("/cocina/on", methods=["GET", "POST"])
def cocina_on():
    light = state.lights["cocina"]
    light.is_on = True
    light.last_update = now()
    send_command_to_esp("/cocina/on")
    return {
        "message": "Luz cocina encendida",
        "light": light,
    }


@app.api_route("/cocina/off", methods=["GET", "POST"])
def cocina_off():
    light = state.lights["cocina"]
    light.is_on = False
    light.last_update = now()
    send_command_to_esp("/cocina/off")
    return {
        "message": "Luz cocina apagada",
        "light": light,
    }


@app.api_route("/sala/on", methods=["GET", "POST"])
def sala_on():
    light = state.lights["sala"]
    light.is_on = True
    light.last_update = now()
    send_command_to_esp("/sala/on")
    return {
        "message": "Luz sala encendida",
        "light": light,
    }


@app.api_route("/sala/off", methods=["GET", "POST"])
def sala_off():
    light = state.lights["sala"]
    light.is_on = False
    light.last_update = now()
    send_command_to_esp("/sala/off")
    return {
        "message": "Luz sala apagada",
        "light": light,
    }


@app.api_route("/dorm/on", methods=["GET", "POST"])
def dorm_on():
    light = state.lights["dorm"]
    light.is_on = True
    light.last_update = now()
    send_command_to_esp("/dorm/on")
    return {
        "message": "Luz dormitorio encendida",
        "light": light,
    }


@app.api_route("/dorm/off", methods=["GET", "POST"])
def dorm_off():
    light = state.lights["dorm"]
    light.is_on = False
    light.last_update = now()
    send_command_to_esp("/dorm/off")
    return {
        "message": "Luz dormitorio apagada",
        "light": light,
    }


# ==========================
# PIR
# ==========================

@app.api_route("/pir/on", methods=["GET", "POST"])
def pir_on():
    state.pir.active = True
    state.pir.last_update = now()
    send_command_to_esp("/pir/on")
    return {
        "message": "PIR activado",
        "pir": state.pir,
    }


@app.api_route("/pir/off", methods=["GET", "POST"])
def pir_off():
    state.pir.active = False
    state.pir.last_update = now()
    send_command_to_esp("/pir/off")
    return {
        "message": "PIR desactivado",
        "pir": state.pir,
    }


# ==========================
# DHT11 (TEMP / HUM)
# ==========================

class DhtUpdate(BaseModel):
    temperature: float
    humidity: float


@app.post("/dht/update")
def dht_update(data: DhtUpdate):
    """
    Endpoint para que el ESP32 mande los valores de temperatura y humedad.
    """
    state.dht.temperature = data.temperature
    state.dht.humidity = data.humidity
    state.dht.last_update = now()
    return {
        "message": "DHT actualizado",
        "dht": state.dht,
    }


@app.get("/dht", response_model=DhtState)
def dht_get():
    """
    Leer los últimos valores de DHT guardados.
    """
    return state.dht


# ==========================
# MODO SEGURO
# ==========================

@app.api_route("/modo/seguro", methods=["GET", "POST"])
def modo_seguro():
    # Apagar luces
    for light in state.lights.values():
        light.is_on = False
        light.last_update = now()

    # Cerrar puertas
    for door in state.doors.values():
        door.is_open = False
        door.last_update = now()

    # Activar PIR, desactivar ultra
    state.pir.active = True
    state.pir.last_update = now()

    state.ultra.active = False
    state.ultra.last_update = now()

    state.modo_seguro = True

    send_command_to_esp("/modo/seguro")

    return {
        "message": "MODO SEGURO ACTIVADO",
        "status": state,
    }
