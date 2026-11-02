.pragma library

var NOISE_MODE_OPTIONS = [
  { value: "cancelacion", label: "Cancelación" },
  { value: "transparencia", label: "Transparencia" },
  { value: "adaptativo", label: "Adaptativo" },
  { value: "desactivado", label: "Desactivado" }
]

function emptyState() {
  return {
    connected: false,
    communicating: false,
    battery: {
      left: { level: null, charging: false },
      right: { level: null, charging: false },
      case: { level: null, charging: false }
    },
    noise_mode: null,
    in_ear: { left: null, right: null },
    ear_detection: true
  }
}

function parseWatchLine(line) {
  var trimmed = String(line || "").trim()
  if (!trimmed) return null
  try {
    var obj = JSON.parse(trimmed)
    if (!obj || typeof obj !== "object") return null
    return {
      connected: obj.connected === true,
      communicating: obj.communicating === true,
      battery: {
        left: normalizePiece(obj.battery && obj.battery.left),
        right: normalizePiece(obj.battery && obj.battery.right),
        case: normalizePiece(obj.battery && obj.battery.case)
      },
      noise_mode: typeof obj.noise_mode === "string" ? obj.noise_mode : null,
      in_ear: {
        left: obj.in_ear && typeof obj.in_ear.left === "boolean" ? obj.in_ear.left : null,
        right: obj.in_ear && typeof obj.in_ear.right === "boolean" ? obj.in_ear.right : null
      },
      ear_detection: obj.ear_detection !== false
    }
  } catch (e) {
    return null
  }
}

function normalizePiece(piece) {
  if (!piece || typeof piece !== "object") {
    return { level: null, charging: false }
  }
  var lvl = (typeof piece.level === "number" && isFinite(piece.level) && piece.level >= 0 && piece.level <= 100)
    ? Math.round(piece.level)
    : null
  return {
    level: lvl,
    charging: piece.charging === true
  }
}

function minEarbudLevel(battery) {
  if (!battery) return null
  var left = battery.left ? battery.left.level : null
  var right = battery.right ? battery.right.level : null
  if (typeof left === "number" && typeof right === "number") {
    return Math.min(left, right)
  }
  if (typeof left === "number") return left
  if (typeof right === "number") return right
  return null
}

function barLabel(state, vertical, icon) {
  var glyph = icon || "󰋋"
  if (!state || !state.connected) return ""
  if (vertical || !state.communicating) return glyph
  var minLvl = minEarbudLevel(state.battery)
  if (minLvl === null) return glyph
  return glyph + " " + minLvl + "%"
}

function formatPieceBattery(piece) {
  if (!piece || piece.level === null || piece.level === undefined) {
    return "Desconocida"
  }
  return piece.level + "%" + (piece.charging ? " · Cargando" : "")
}

function formatInEarPiece(inEarVal) {
  if (inEarVal === true) return "Puesto"
  if (inEarVal === false) return "Fuera"
  return "Desconocido"
}
