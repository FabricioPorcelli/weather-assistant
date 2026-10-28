"""Umbrales y niveles configurables del motor."""

from dataclasses import dataclass
from typing import Final

# Paraguas: probabilidad en porcentaje y lluvia en milímetros.
UMBRELLA_YES_PROBABILITY: Final = 50
UMBRELLA_YES_MM: Final = 1.0
UMBRELLA_MAYBE_PROBABILITY: Final = 25
UMBRELLA_MAYBE_MM: Final = 0.2

# Ropa: viento en km/h y amplitud térmica en °C.
WIND_ADJUSTMENT_KMH: Final = 30.0
TEMPERATURE_RANGE_C: Final = 10.0
DEFAULT_COMFORT_OFFSET_C: Final = 0.0


@dataclass(frozen=True, slots=True)
class ClothingLevel:
    """Un nivel de abrigo y el umbral mínimo de temperatura que lo activa."""

    min_temperature_c: float
    verdict: str
    description: str


CLOTHING_LEVELS: Final[tuple[ClothingLevel, ...]] = (
    ClothingLevel(28.0, "muy_liviana", "ropa muy liviana y protector solar"),
    ClothingLevel(22.0, "liviana", "ropa liviana"),
    ClothingLevel(16.0, "capa_intermedia", "capa intermedia (buzo o manga larga)"),
    ClothingLevel(10.0, "campera", "campera"),
    ClothingLevel(4.0, "abrigo_con_bufanda", "abrigo y bufanda"),
    ClothingLevel(float("-inf"), "abrigo_grueso", "abrigo grueso, gorro y guantes"),
)

# Riego: lluvia en milímetros y temperatura máxima en °C.
WATERING_SOIL_WET_MM: Final = 10.0
WATERING_UPCOMING_PROBABILITY: Final = 60
WATERING_UPCOMING_MM: Final = 5.0
WATERING_HOT_TEMP_C: Final = 30.0
WATERING_HOT_DRY_MM: Final = 2.0
WATERING_MILD_TEMP_C: Final = 20.0
WATERING_MILD_DRY_MM: Final = 5.0

# Actividades: puntaje de 0 a 100.
ACTIVITY_IDEAL_MIN_SCORE: Final = 80
ACTIVITY_ACCEPTABLE_MIN_SCORE: Final = 50
ACTIVITY_TEMPERATURE_PENALTY_PER_C: Final = 5
ACTIVITY_MAX_TEMPERATURE_PENALTY: Final = 60

# Confianza por horizonte, expresada como días de diferencia con el primer día.
CONFIDENCE_HIGH_MAX_OFFSET: Final = 2
CONFIDENCE_MEDIUM_MAX_OFFSET: Final = 6
