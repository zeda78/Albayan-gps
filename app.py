from flask import Flask, request, jsonify, render_template_string
import math

app = Flask(__name__)

# ═══════════════════════════════════════════════════════════════
# توليد الأبراج الافتراضية - 3 أبراج فقط
# ═══════════════════════════════════════════════════════════════
class TowerGenerator:
    @staticmethod
    def generate_virtual_towers(main_lat, main_lon, main_distance, final_angle):
        towers = []
        # 3 أبراج موزعة حول اتجاه قطاع الإشارة
        angles = [final_angle - 60, final_angle, final_angle + 60]
        for i, angle in enumerate(angles):
            dist_factor = 1.0 + (0.15 * (1 - i))
            tower_dist = main_distance * dist_factor
            tower_lat, tower_lon = move(main_lat, main_lon, angle, tower_dist)
            real_dist = haversine(main_lat, main_lon, tower_lat, tower_lon)
            est_signal = -85 - (abs(i - 1) * 7)
            towers.append({
                'lat': round(tower_lat, 6),
                'lon': round(tower_lon, 6),
                'distance_from_main': round(real_dist, 1),
                'angle': round(angle, 1),
                'signal_dbm': est_signal,
                'virtual': True,
                'tower_id': f'VT{i+1}',
                'weight': round(0.6 - (abs(i - 1) * 0.1), 2),
                'label': f'برج افتراضي {i+1}'
            })
        return towers

class CellIDAnalyzer:
    SECTOR_PATTERNS = {
        'almadar': {
            0: {'angle': 0, 'direction': 'شمال', 'sector': 'Sector-1'},
            1: {'angle': 60, 'direction': 'شمال شرق', 'sector': 'Sector-2'},
            2: {'angle': 120, 'direction': 'جنوب شرق', 'sector': 'Sector-3'},
            3: {'angle': 180, 'direction': 'جنوب', 'sector': 'Sector-4'},
            4: {'angle': 240, 'direction': 'جنوب غرب', 'sector': 'Sector-5'},
            5: {'angle': 300, 'direction': 'شمال غرب', 'sector': 'Sector-6'}
        },
        'libyana': {
            0: {'angle': 0, 'direction': 'شمال', 'sector': 'Alpha'},
            1: {'angle': 120, 'direction': 'جنوب شرق', 'sector': 'Beta'},
            2: {'angle': 240, 'direction': 'جنوب غرب', 'sector': 'Gamma'}
        }
    }
    DIRECTION_ANGLES = {
        'شمال': 0, 'شمال شرق': 45, 'شرق': 90, 'جنوب شرق': 135,
        'جنوب': 180, 'جنوب غرب': 225, 'غرب': 270, 'شمال غرب': 315
    }

    @staticmethod
    def parse_cell_id(cell_input):
        cell_input = cell_input.strip()
        result = {
            'raw': cell_input, 'mcc': None, 'mnc': None, 'lac': None, 'cid': None,
            'provider': 'غير معروف', 'angle_info': None, 'format': 'غير معروف'
        }
        if '-' in cell_input:
            parts = cell_input.replace(' ', '').split('-')
            if len(parts) == 4:
                try:
                    result['mcc'] = int(parts[0])
                    result['mnc'] = int(parts[1])
                    result['lac'] = int(parts[2])
                    result['cid'] = int(parts[3])
                    result['format'] = 'عشري قياسي'
                    if result['mcc'] == 606:
                        if result['mnc'] == 0:
                            result['provider'] = 'Libyana'
                        elif result['mnc'] == 1:
                            result['provider'] = 'Al-Madar'
                    result['angle_info'] = CellIDAnalyzer.extract_angle_from_cid(result['cid'], result['provider'])
                except:
                    pass
        return result

    @staticmethod
    def extract_angle_from_cid(cid, provider):
        provider_key = 'libyana' if 'libyana' in provider.lower() else 'almadar'
        patterns = CellIDAnalyzer.SECTOR_PATTERNS.get(provider_key, CellIDAnalyzer.SECTOR_PATTERNS['almadar'])
        if provider_key == 'libyana':
            sector_id = cid % 3
        else:
            sector_id = cid % 6
        angle_data = patterns.get(sector_id, {'angle': 0, 'direction': 'شمال', 'sector': 'Unknown'})
        return {
            'sector_id': sector_id,
            'angle': angle_data['angle'],
            'direction': angle_data['direction'],
            'sector_name': angle_data['sector'],
            'method': f'CID mod {3 if provider_key == "libyana" else 6}'
        }

    @staticmethod
    def refine_angle(user_direction, extracted_angle_info):
        if not extracted_angle_info:
            return None, "لا يوجد زاوية مستخرجة"
        user_angle = CellIDAnalyzer.DIRECTION_ANGLES.get(user_direction, None)
        if user_angle is None:
            return extracted_angle_info['angle'], "زاوية مستخرجة فقط"
        extracted_angle = extracted_angle_info['angle']
        angle_diff = abs(user_angle - extracted_angle)
        if angle_diff > 180:
            angle_diff = 360 - angle_diff
        if angle_diff <= 30:
            refined = (user_angle + extracted_angle) / 2
            return refined, f"تطابق عالي (فرق {angle_diff}°)"
        elif angle_diff <= 90:
            return user_angle, f"تصحيح جزئي (فرق {angle_diff}°)"
        else:
            return user_angle, f"تعارض كبير (فرق {angle_diff}°)"

def hata_urban(rssi_dbm, freq_mhz=900):
    eirp_dbm = 46 + 15
    L = eirp_dbm - rssi_dbm
    a_hm = (1.1 * math.log10(freq_mhz) - 0.7) * 1.5 - (1.56 * math.log10(freq_mhz) - 0.8)
    A = 69.55 + 26.16 * math.log10(freq_mhz) - 13.82 * math.log10(30) - a_hm
    B = 44.9 - 6.55 * math.log10(30)
    log10_d = (L - A) / B
    if log10_d < -2: return 10
    elif log10_d > 1.5: return 30000
    return math.pow(10, log10_d) * 1000

def cost231_hata(rssi_dbm, freq_mhz=1800):
    eirp_dbm = 46 + 15
    L = eirp_dbm - rssi_dbm
    a_hm = (1.1 * math.log10(freq_mhz) - 0.7) * 1.5 - (1.56 * math.log10(freq_mhz) - 0.8)
    C = 3 if freq_mhz >= 1500 else 0
    A = 46.3 + 33.9 * math.log10(freq_mhz) - 13.82 * math.log10(30) - a_hm + C
    B = 44.9 - 6.55 * math.log10(30)
    log10_d = (L - A) / B
    if log10_d < -2: return 10
    elif log10_d > 1.5: return 30000
    return math.pow(10, log10_d) * 1000

def smart_distance_estimate(rssi_dbm, freq_mhz=900, environment="urban"):
    d_hata = hata_urban(rssi_dbm, freq_mhz)
    d_cost = cost231_hata(rssi_dbm, freq_mhz)
    if environment == "urban":
        base = d_cost if freq_mhz >= 1500 else d_hata
        correction = 0.85 if freq_mhz >= 1500 else 0.80
    elif environment == "suburban":
        base = (d_hata + d_cost) / 2
        correction = 1.15
    elif environment == "rural":
        base = d_hata
        correction = 1.25
    elif environment == "indoor":
        base = d_hata
        correction = 0.45
    else:
        base = (d_hata + d_cost) / 2
        correction = 1.0
    return base * correction

def move(lat, lon, angle, distance):
    R = 6371000
    rad = math.radians(angle)
    dlat = (distance / R) * math.cos(rad)
    dlon = (distance / R) * math.sin(rad) / math.cos(math.radians(lat))
    return (lat + math.degrees(dlat), lon + math.degrees(dlon))

def haversine(lat1, lon1, lat2, lon2):
    R = 6371000
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat/2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon/2)**2
    c = 2 * math.asin(math.sqrt(a))
    return R * c

def least_squares_trilateration(towers):
    if len(towers) < 3:
        return None
    lat_sum, lon_sum, w_sum = 0, 0, 0
    for t in towers:
        w = 1.0 / max(t['distance'], 1)
        lat_sum += t['lat'] * w
        lon_sum += t['lon'] * w
        w_sum += w
    x = lat_sum / w_sum
    y = lon_sum / w_sum
    learning_rate = 0.001
    for _ in range(100):
        grad_x, grad_y = 0, 0
        for t in towers:
            dx = (x - t['lat']) * 111000
            dy = (y - t['lon']) * 111000 * math.cos(math.radians(t['lat']))
            dist = math.sqrt(dx**2 + dy**2)
            if dist > 1:
                error = dist - t['distance']
                grad_x += 2 * error * dx / dist / 111000
                grad_y += 2 * error * dy / dist / (111000 * math.cos(math.radians(t['lat'])))
        x -= learning_rate * grad_x
        y -= learning_rate * grad_y
    return {'lat': x, 'lon': y}

def weighted_centroid_trilateration(towers):
    if len(towers) < 2:
        return None
    total_weight = 0
    weighted_lat = 0
    weighted_lon = 0
    for t in towers:
        weight = t.get('weight', 1.0) / max(t['distance'], 100)
        weighted_lat += t['lat'] * weight
        weighted_lon += t['lon'] * weight
        total_weight += weight
    if total_weight == 0:
        return None
    return {'lat': weighted_lat / total_weight, 'lon': weighted_lon / total_weight}

def calculate_confidence(towers_used, signal_quality, environment, angle_refinement_quality):
    base_score = 0.0
    if towers_used >= 4: base_score += 35
    elif towers_used == 3: base_score += 25
    elif towers_used == 2: base_score += 15
    else: base_score += 8
    if signal_quality >= -70: base_score += 20
    elif signal_quality >= -85: base_score += 15
    elif signal_quality >= -100: base_score += 10
    else: base_score += 5
    env_scores = {'rural': 10, 'suburban': 8, 'urban': 5, 'indoor': 2}
    base_score += env_scores.get(environment, 5)
    if angle_refinement_quality == 'high': base_score += 15
    elif angle_refinement_quality == 'medium': base_score += 10
    elif angle_refinement_quality == 'low': base_score += 5
    return min(base_score, 100)


# ═══════════════════════════════════════════════════════════════
# HTML Template - واجهة مع خريطة قمر صناعي + مؤشر بصري + أسماء
# ═══════════════════════════════════════════════════════════════
HTML_TEMPLATE = '''
<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>نظام تحديد المواقع الليبي - خريطة مدمجة</title>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<style>
@import url('https://fonts.googleapis.com/css2?family=Cairo:wght@300;400;600;700;800&display=swap');
* { margin: 0; padding: 0; box-sizing: border-box; }

:root {
    --primary: #2563eb;
    --primary-dark: #1d4ed8;
    --success: #10b981;
    --warning: #f59e0b;
    --danger: #ef4444;
    --info: #06b6d4;
    --virtual: #8b5cf6;
    --main: #f97316;
    --phone: #ec4899;
    --bg: #0f172a;
    --card: #1e293b;
    --border: #334155;
    --text: #f1f5f9;
    --text-muted: #94a3b8;
}

body {
    background: var(--bg);
    color: var(--text);
    font-family: 'Cairo', sans-serif;
    min-height: 100vh;
    direction: rtl;
}

.container {
    max-width: 1600px;
    margin: 0 auto;
    padding: 15px;
}

.header {
    text-align: center;
    padding: 20px 0;
    border-bottom: 2px solid var(--border);
    margin-bottom: 20px;
}

.header h1 {
    font-size: 2em;
    font-weight: 800;
    background: linear-gradient(135deg, var(--primary), var(--success));
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
}

.header p {
    color: var(--text-muted);
    font-size: 1em;
    margin-top: 5px;
}

.grid {
    display: grid;
    grid-template-columns: 380px 1fr;
    gap: 20px;
    height: calc(100vh - 140px);
}

@media (max-width: 1000px) {
    .grid { grid-template-columns: 1fr; height: auto; }
}

.sidebar {
    overflow-y: auto;
    padding-right: 5px;
}

.sidebar::-webkit-scrollbar { width: 6px; }
.sidebar::-webkit-scrollbar-track { background: var(--bg); }
.sidebar::-webkit-scrollbar-thumb { background: var(--primary); border-radius: 3px; }

.card {
    background: var(--card);
    border-radius: 14px;
    padding: 20px;
    border: 1px solid var(--border);
    margin-bottom: 15px;
}

.card-title {
    font-size: 1.1em;
    font-weight: 700;
    color: var(--primary);
    margin-bottom: 15px;
    padding-bottom: 8px;
    border-bottom: 2px solid var(--border);
    display: flex;
    align-items: center;
    gap: 8px;
}

.form-group {
    margin-bottom: 14px;
}

.form-group label {
    display: block;
    font-weight: 600;
    margin-bottom: 6px;
    color: var(--text-muted);
    font-size: 0.9em;
}

input, select {
    width: 100%;
    padding: 10px 12px;
    border-radius: 8px;
    border: 1px solid var(--border);
    background: #0f172a;
    color: var(--text);
    font-family: 'Cairo', sans-serif;
    font-size: 0.95em;
}

input:focus, select:focus {
    outline: none;
    border-color: var(--primary);
    box-shadow: 0 0 0 2px rgba(37, 99, 235, 0.2);
}

.btn {
    width: 100%;
    padding: 12px;
    border-radius: 10px;
    border: none;
    font-family: 'Cairo', sans-serif;
    font-size: 1em;
    font-weight: 700;
    cursor: pointer;
    transition: all 0.3s;
}

.btn-primary {
    background: linear-gradient(135deg, var(--primary), var(--primary-dark));
    color: white;
}

.btn-primary:hover {
    transform: translateY(-2px);
    box-shadow: 0 6px 20px rgba(37, 99, 235, 0.4);
}

.map-container {
    background: var(--card);
    border-radius: 14px;
    border: 1px solid var(--border);
    overflow: hidden;
    position: relative;
    height: 100%;
}

#map {
    height: 100%;
    width: 100%;
    background: #1a1a2e;
}

.map-legend {
    position: absolute;
    bottom: 20px;
    right: 20px;
    background: rgba(15, 23, 42, 0.95);
    padding: 15px;
    border-radius: 10px;
    border: 1px solid var(--border);
    z-index: 1000;
    min-width: 200px;
    backdrop-filter: blur(10px);
}

.map-legend h4 {
    color: var(--primary);
    margin-bottom: 10px;
    font-size: 0.9em;
}

.legend-item {
    display: flex;
    align-items: center;
    gap: 8px;
    margin: 6px 0;
    font-size: 0.85em;
    color: var(--text-muted);
}

.legend-icon {
    width: 14px;
    height: 14px;
    border-radius: 50%;
    border: 2px solid;
    flex-shrink: 0;
}

.legend-line {
    width: 20px;
    height: 2px;
    flex-shrink: 0;
}

.result-section {
    display: none;
}

.result-section.active {
    display: block;
    animation: fadeIn 0.5s ease;
}

@keyframes fadeIn {
    from { opacity: 0; transform: translateY(10px); }
    to { opacity: 1; transform: translateY(0); }
}

.tower-mini {
    background: rgba(139, 92, 246, 0.1);
    border: 1px solid var(--virtual);
    border-radius: 8px;
    padding: 10px;
    margin: 8px 0;
    font-size: 0.85em;
}

.tower-mini h5 {
    color: var(--virtual);
    margin-bottom: 5px;
    font-size: 0.95em;
}

.tower-mini-row {
    display: flex;
    justify-content: space-between;
    padding: 2px 0;
    color: var(--text-muted);
}

.tower-mini-value {
    color: var(--text);
    font-weight: 600;
    direction: ltr;
}

.main-tower-mini {
    background: rgba(249, 115, 22, 0.1);
    border-color: var(--main);
}

.main-tower-mini h5 {
    color: var(--main);
}

.phone-mini {
    background: rgba(236, 72, 153, 0.1);
    border-color: var(--phone);
}

.phone-mini h5 {
    color: var(--phone);
}

.stats-row {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 10px;
    margin: 10px 0;
}

.stat-mini {
    background: rgba(0,0,0,0.2);
    padding: 10px;
    border-radius: 8px;
    text-align: center;
}

.stat-mini-value {
    font-size: 1.3em;
    font-weight: 700;
    color: var(--primary);
}

.stat-mini-label {
    font-size: 0.8em;
    color: var(--text-muted);
    margin-top: 3px;
}

.confidence-bar {
    width: 100%;
    height: 8px;
    background: rgba(255,255,255,0.1);
    border-radius: 4px;
    overflow: hidden;
    margin: 8px 0;
}

.confidence-fill {
    height: 100%;
    border-radius: 4px;
    transition: width 1s ease;
}

.conf-high { background: linear-gradient(90deg, var(--success), #34d399); }
.conf-medium { background: linear-gradient(90deg, var(--warning), #fbbf24); }
.conf-low { background: linear-gradient(90deg, var(--danger), #f87171); }

.badge {
    display: inline-block;
    padding: 3px 10px;
    border-radius: 15px;
    font-size: 0.8em;
    font-weight: 600;
}

.badge-success { background: rgba(16, 185, 129, 0.2); color: var(--success); }
.badge-warning { background: rgba(245, 158, 11, 0.2); color: var(--warning); }
.badge-danger { background: rgba(239, 68, 68, 0.2); color: var(--danger); }

.loading {
    display: none;
    text-align: center;
    padding: 30px;
}

.loading.active {
    display: block;
}

.spinner {
    border: 3px solid rgba(37, 99, 235, 0.2);
    border-top: 3px solid var(--primary);
    border-radius: 50%;
    width: 40px;
    height: 40px;
    animation: spin 1s linear infinite;
    margin: 0 auto 15px;
}

@keyframes spin {
    0% { transform: rotate(0deg); }
    100% { transform: rotate(360deg); }
}

.error-msg {
    background: rgba(239, 68, 68, 0.1);
    border: 1px solid var(--danger);
    color: var(--danger);
    padding: 12px;
    border-radius: 8px;
    margin: 10px 0;
    display: none;
    font-size: 0.9em;
}

.error-msg.active { display: block; }

.coords-box {
    background: rgba(0,0,0,0.3);
    padding: 12px;
    border-radius: 8px;
    font-family: monospace;
    font-size: 1em;
    direction: ltr;
    text-align: right;
    margin: 10px 0;
    border: 1px solid var(--border);
    color: var(--success);
}

.pulse-animation {
    animation: pulse 2s infinite;
}

@keyframes pulse {
    0% { box-shadow: 0 0 0 0 rgba(236, 72, 153, 0.7); }
    70% { box-shadow: 0 0 0 15px rgba(236, 72, 153, 0); }
    100% { box-shadow: 0 0 0 0 rgba(236, 72, 153, 0); }
}
</style>
</head>
<body>
<div class="container">
    <div class="header">
        <h1>🇱🇾 نظام تحديد المواقع الليبي</h1>
        <p>خريطة قمر صناعي مدمجة - توليد 3 أبراج افتراضية - تثليث دقيق</p>
    </div>

    <div class="grid">
        <!-- Sidebar -->
        <div class="sidebar">
            <div class="card">
                <div class="card-title">📡 بيانات البرج الأساسي</div>
                <div class="form-group">
                    <label>🔢 معرف الخلية (Cell ID)</label>
                    <input type="text" id="cellId" placeholder="606-01-1021-8973" value="606-01-1021-8973">
                </div>
                <div class="form-group">
                    <label>📍 خط العرض (Latitude)</label>
                    <input type="number" id="lat" step="any" placeholder="32.853826" value="32.853826">
                </div>
                <div class="form-group">
                    <label>📍 خط الطول (Longitude)</label>
                    <input type="number" id="lon" step="any" placeholder="13.241509" value="13.241509">
                </div>
            </div>

            <div class="card">
                <div class="card-title">⚙️ إعدادات الإشارة</div>
                <div class="form-group">
                    <label>🧭 اتجاه قطاع الإشارة من البرج</label>
                    <select id="direction">
                        <option value="auto">🔍 استخراج تلقائي من Cell ID</option>
                        <option value="شمال">🧭 شمال (0°)</option>
                        <option value="شمال شرق">↗️ شمال شرق (45°)</option>
                        <option value="شرق">➡️ شرق (90°)</option>
                        <option value="جنوب شرق">↘️ جنوب شرق (135°)</option>
                        <option value="جنوب">⬇️ جنوب (180°)</option>
                        <option value="جنوب غرب">↙️ جنوب غرب (225°)</option>
                        <option value="غرب">⬅️ غرب (270°)</option>
                        <option value="شمال غرب">↖️ شمال غرب (315°)</option>
                    </select>
                </div>
                <div class="form-group">
                    <label>📶 قوة الإشارة</label>
                    <select id="signal">
                        <option value="-50">📶 ممتازة (-50 dBm)</option>
                        <option value="-65">📶 قوية (-65 dBm)</option>
                        <option value="-80" selected>📶 متوسطة (-80 dBm)</option>
                        <option value="-95">📶 ضعيفة (-95 dBm)</option>
                        <option value="-110">📶 ضعيفة جداً (-110 dBm)</option>
                    </select>
                </div>
                <div class="form-group">
                    <label>🏙️ نوع البيئة</label>
                    <select id="environment">
                        <option value="urban">🏙️ حضرية</option>
                        <option value="suburban">🏘️ ضواحي</option>
                        <option value="rural">🌾 ريفية</option>
                        <option value="indoor">🏢 داخل مبنى</option>
                    </select>
                </div>
                <div class="form-group">
                    <label>📡 التردد</label>
                    <select id="freq">
                        <option value="900">📶 GSM 900 MHz</option>
                        <option value="1800">📶 GSM/LTE 1800 MHz</option>
                        <option value="2100">📶 UMTS 2100 MHz</option>
                        <option value="2600">📶 LTE 2600 MHz</option>
                    </select>
                </div>
                <button class="btn btn-primary" onclick="locate()">🎯 تحديد الموقع على الخريطة</button>
            </div>

            <div class="loading" id="loading">
                <div class="spinner"></div>
                <p>⏳ جاري التحليل...</p>
            </div>

            <div class="error-msg" id="errorMsg"></div>

            <!-- Results -->
            <div class="result-section" id="results">
                <div class="card">
                    <div class="card-title">🔍 تحليل Cell ID</div>
                    <div id="cellAnalysis"></div>
                </div>

                <div class="card">
                    <div class="card-title">📶 الإشارة والمسافة</div>
                    <div id="signalAnalysis"></div>
                </div>

                <div class="card">
                    <div class="card-title">🤖 الأبراج الافتراضية (3)</div>
                    <div id="towerList"></div>
                </div>

                <div class="card">
                    <div class="card-title">🎯 نتيجة التثليث</div>
                    <div id="triResult"></div>
                </div>

                <div class="card">
                    <div class="card-title">✅ الموقع النهائي</div>
                    <div id="finalResult"></div>
                </div>
            </div>
        </div>

        <!-- Map -->
        <div class="map-container">
            <div id="map"></div>
            <div class="map-legend">
                <h4>🗺️ دليل الخريطة</h4>
                <div class="legend-item">
                    <div class="legend-icon" style="background:#f97316;border-color:#f97316;"></div>
                    <span>📡 البرج الأساسي (أنت)</span>
                </div>
                <div class="legend-item">
                    <div class="legend-icon" style="background:#8b5cf6;border-color:#8b5cf6;"></div>
                    <span>🤖 أبراج افتراضية (3)</span>
                </div>
                <div class="legend-item">
                    <div class="legend-icon" style="background:#ec4899;border-color:#ec4899;"></div>
                    <span>📱 موقع الهاتف المقدر</span>
                </div>
                <div class="legend-item">
                    <div class="legend-line" style="background:#06b6d4;"></div>
                    <span>〰️ خطوط الاتصال</span>
                </div>
                <div class="legend-item">
                    <div class="legend-line" style="background:rgba(236,72,153,0.3);height:8px;border-radius:2px;"></div>
                    <span>🎯 منطقة الاحتمال</span>
                </div>
                <div class="legend-item">
                    <div class="legend-line" style="background:#fbbf24;height:3px;"></div>
                    <span>🧭 اتجاه قطاع الإشارة</span>
                </div>
            </div>
        </div>
    </div>
</div>
'''


# ═══════════════════════════════════════════════════════════════
# JavaScript - خريطة Leaflet مع مؤشر بصري واتجاه القطاع
# ═══════════════════════════════════════════════════════════════
JS_CODE = '''
<script>
let map = null;
let markers = [];
let polylines = [];
let polygons = [];
let sectorLines = [];

// إنشاء الخريطة
function initMap() {
    map = L.map('map', {
        center: [32.8538, 13.2415],
        zoom: 6,
        zoomControl: true,
        attributionControl: false
    });

    // طبقة القمر الصناعي (Esri World Imagery)
    L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}', {
        attribution: 'Esri',
        maxZoom: 19
    }).addTo(map);

    // طبقة التسميات (أسماء المدن والطرق)
    L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/Reference/World_Boundaries_and_Places/MapServer/tile/{z}/{y}/{x}', {
        attribution: 'Esri',
        maxZoom: 19
    }).addTo(map);
}

// تنظيف الطبقات القديمة
function clearMap() {
    markers.forEach(m => map.removeLayer(m));
    polylines.forEach(p => map.removeLayer(p));
    polygons.forEach(p => map.removeLayer(p));
    sectorLines.forEach(s => map.removeLayer(s));
    markers = [];
    polylines = [];
    polygons = [];
    sectorLines = [];
}

// أيقونة البرج الأساسي
function createMainTowerIcon() {
    return L.divIcon({
        html: `<div style="background:linear-gradient(135deg,#f97316,#fb923c);width:28px;height:28px;border-radius:50%;border:3px solid white;box-shadow:0 0 15px rgba(249,115,22,0.7);display:flex;align-items:center;justify-content:center;font-size:14px;">📡</div>`,
        iconSize: [28, 28],
        iconAnchor: [14, 14],
        className: 'main-tower-marker'
    });
}

// أيقونة البرج الافتراضي
function createVirtualTowerIcon(num) {
    return L.divIcon({
        html: `<div style="background:linear-gradient(135deg,#8b5cf6,#a78bfa);width:24px;height:24px;border-radius:50%;border:2px solid white;box-shadow:0 0 12px rgba(139,92,246,0.6);display:flex;align-items:center;justify-content:center;font-size:12px;font-weight:700;color:white;">${num}</div>`,
        iconSize: [24, 24],
        iconAnchor: [12, 12],
        className: 'virtual-tower-marker'
    });
}

// أيقونة الهاتف
function createPhoneIcon() {
    return L.divIcon({
        html: `<div style="background:linear-gradient(135deg,#ec4899,#f472b6);width:32px;height:32px;border-radius:50%;border:3px solid white;box-shadow:0 0 20px rgba(236,72,153,0.8);display:flex;align-items:center;justify-content:center;font-size:16px;animation:pulse 2s infinite;">📱</div>`,
        iconSize: [32, 32],
        iconAnchor: [16, 16],
        className: 'phone-marker'
    });
}

// رسم مؤشر بصري (Visual Indicator) - سهم يشير لاتجاه القطاع
function drawSectorIndicator(lat, lon, angle, distance, color = '#fbbf24') {
    // حساب نقطة نهاية السهم
    const R = 6371000;
    const rad = angle * Math.PI / 180;
    const arrowDist = distance * 0.3; // السهم يمتد 30% من المسافة
    const dlat = (arrowDist / R) * Math.cos(rad);
    const dlon = (arrowDist / R) * Math.sin(rad) / Math.cos(lat * Math.PI / 180);
    const endLat = lat + (dlat * 180 / Math.PI);
    const endLon = lon + (dlon * 180 / Math.PI);

    // السهم الرئيسي
    const arrow = L.polyline(
        [[lat, lon], [endLat, endLon]],
        {color: color, weight: 4, opacity: 0.9, lineCap: 'round'}
    ).addTo(map);
    sectorLines.push(arrow);

    // رأس السهم (مثلث صغير)
    const headAngle1 = (angle + 150) * Math.PI / 180;
    const headAngle2 = (angle - 150) * Math.PI / 180;
    const headDist = arrowDist * 0.15;

    const headLat1 = endLat + ((headDist / R) * Math.cos(headAngle1) * 180 / Math.PI);
    const headLon1 = endLon + ((headDist / R) * Math.sin(headAngle1) * 180 / Math.PI / Math.cos(endLat * Math.PI / 180));
    const headLat2 = endLat + ((headDist / R) * Math.cos(headAngle2) * 180 / Math.PI);
    const headLon2 = endLon + ((headDist / R) * Math.sin(headAngle2) * 180 / Math.PI / Math.cos(endLat * Math.PI / 180));

    const arrowHead = L.polygon(
        [[endLat, endLon], [headLat1, headLon1], [headLat2, headLon2]],
        {color: color, fillColor: color, fillOpacity: 0.9, weight: 1}
    ).addTo(map);
    sectorLines.push(arrowHead);

    // دائرة صغيرة عند نقطة البداية
    const startCircle = L.circleMarker([lat, lon], {
        radius: 6,
        color: color,
        fillColor: color,
        fillOpacity: 1,
        weight: 2
    }).addTo(map);
    sectorLines.push(startCircle);

    return {endLat, endLon};
}

// رسم قطاع الإشارة (Sector Arc)
function drawSectorArc(lat, lon, angle, distance, width = 120) {
    const points = [];
    const R = 6371000;
    const startAngle = angle - width/2;
    const endAngle = angle + width/2;
    const steps = 20;

    for (let i = 0; i <= steps; i++) {
        const a = (startAngle + (endAngle - startAngle) * i / steps) * Math.PI / 180;
        const dlat = (distance / R) * Math.cos(a);
        const dlon = (distance / R) * Math.sin(a) / Math.cos(lat * Math.PI / 180);
        points.push([lat + (dlat * 180 / Math.PI), lon + (dlon * 180 / Math.PI)]);
    }

    // إضافة نقطة المركز لإغلاق القطاع
    points.push([lat, lon]);

    const sector = L.polygon(points, {
        color: '#fbbf24',
        fillColor: '#fbbf24',
        fillOpacity: 0.1,
        weight: 2,
        dashArray: '5,5'
    }).addTo(map);
    sectorLines.push(sector);
}

// رسم النتائج على الخريطة
function drawOnMap(data) {
    clearMap();

    const main = data.towers.main;
    const virtual = data.towers.virtual;
    const final = data.final_result;
    const sectorAngle = main.final_angle;
    const sectorDist = main.estimated_distance;

    // 1. رسم مؤشر اتجاه قطاع الإشارة (الجديد)
    drawSectorIndicator(main.lat, main.lon, sectorAngle, sectorDist, '#fbbf24');
    drawSectorArc(main.lat, main.lon, sectorAngle, sectorDist, 120);

    // 2. البرج الأساسي
    const mainMarker = L.marker([main.lat, main.lon], {icon: createMainTowerIcon()})
        .addTo(map)
        .bindPopup(`
            <div style="text-align:center;font-family:Cairo,sans-serif;">
                <h3 style="color:#f97316;margin:0;">📡 البرج الأساسي</h3>
                <p style="margin:5px 0;"><b>الإحداثيات:</b><br>${main.lat}, ${main.lon}</p>
                <p style="margin:5px 0;"><b>المسافة المقدرة:</b> ${main.estimated_distance.toFixed(0)} م</p>
                <p style="margin:5px 0;"><b>اتجاه القطاع:</b> ${main.final_angle.toFixed(1)}°</p>
                <p style="margin:5px 0;"><b>عرض القطاع:</b> 120°</p>
            </div>
        `, {maxWidth: 250});
    markers.push(mainMarker);

    // 3. الأبراج الافتراضية (داخل اتجاه القطاع)
    virtual.forEach((vt, i) => {
        const vtMarker = L.marker([vt.lat, vt.lon], {icon: createVirtualTowerIcon(i+1)})
            .addTo(map)
            .bindPopup(`
                <div style="text-align:center;font-family:Cairo,sans-serif;">
                    <h3 style="color:#8b5cf6;margin:0;">🤖 ${vt.label}</h3>
                    <p style="margin:5px 0;"><b>الإحداثيات:</b><br>${vt.lat}, ${vt.lon}</p>
                    <p style="margin:5px 0;"><b>المسافة من البرج:</b> ${vt.distance_from_main.toFixed(1)} م</p>
                    <p style="margin:5px 0;"><b>الزاوية داخل القطاع:</b> ${vt.angle}°</p>
                    <p style="margin:5px 0;"><b>قوة الإشارة:</b> ${vt.signal_dbm} dBm</p>
                </div>
            `, {maxWidth: 250});
        markers.push(vtMarker);

        // خط من البرج الأساسي إلى البرج الافتراضي (داخل القطاع)
        const line = L.polyline(
            [[main.lat, main.lon], [vt.lat, vt.lon]],
            {color: '#06b6d4', weight: 2, opacity: 0.7, dashArray: '5,5'}
        ).addTo(map);
        polylines.push(line);
    });

    // 4. موقع الهاتف (داخل اتجاه القطاع)
    const phoneMarker = L.marker([final.lat, final.lon], {icon: createPhoneIcon()})
        .addTo(map)
        .bindPopup(`
            <div style="text-align:center;font-family:Cairo,sans-serif;">
                <h3 style="color:#ec4899;margin:0;">📱 موقع الهاتف المقدر</h3>
                <p style="margin:5px 0;"><b>الإحداثيات:</b><br>${final.lat.toFixed(6)}, ${final.lon.toFixed(6)}</p>
                <p style="margin:5px 0;"><b>المسافة من البرج:</b> ${final.distance_from_main.toFixed(0)} م</p>
                <p style="margin:5px 0;"><b>الزاوية داخل القطاع:</b> ${final.angle.toFixed(1)}°</p>
                <p style="margin:5px 0;"><b>الثقة:</b> ${data.triangulation.confidence}%</p>
            </div>
        `, {maxWidth: 250});
    markers.push(phoneMarker);

    // 5. خطوط من الأبراج الافتراضية إلى الهاتف
    virtual.forEach(vt => {
        const line = L.polyline(
            [[vt.lat, vt.lon], [final.lat, final.lon]],
            {color: '#ec4899', weight: 1.5, opacity: 0.4, dashArray: '3,7'}
        ).addTo(map);
        polylines.push(line);
    });

    // 6. خط من البرج الأساسي إلى الهاتف (داخل القطاع)
    const mainLine = L.polyline(
        [[main.lat, main.lon], [final.lat, final.lon]],
        {color: '#f97316', weight: 3, opacity: 0.8}
    ).addTo(map);
    polylines.push(mainLine);

    // 7. منطقة الاحتمال (مثلث بين الأبراج)
    const sectorPoints = [
        [main.lat, main.lon],
        [virtual[0].lat, virtual[0].lon],
        [virtual[2].lat, virtual[2].lon]
    ];
    const sectorPoly = L.polygon(sectorPoints, {
        color: '#ec4899',
        fillColor: '#ec4899',
        fillOpacity: 0.08,
        weight: 1.5,
        dashArray: '5,5'
    }).addTo(map);
    polygons.push(sectorPoly);

    // 8. تكبير الخريطة
    const bounds = L.latLngBounds([
        [main.lat, main.lon],
        [final.lat, final.lon]
    ]);
    virtual.forEach(vt => bounds.extend([vt.lat, vt.lon]));
    map.fitBounds(bounds, {padding: [100, 100]});
}

// عرض النتائج في الشريط الجانبي
function displayResults(data) {
    // تحليل Cell ID
    const ca = data.cell_analysis;
    document.getElementById('cellAnalysis').innerHTML = `
        <div class="stats-row">
            <div class="stat-mini"><div class="stat-mini-value">${ca.provider}</div><div class="stat-mini-label">المزود</div></div>
            <div class="stat-mini"><div class="stat-mini-value">${ca.mcc||'--'}</div><div class="stat-mini-label">MCC</div></div>
        </div>
        <div class="stats-row">
            <div class="stat-mini"><div class="stat-mini-value">${ca.mnc||'--'}</div><div class="stat-mini-label">MNC</div></div>
            <div class="stat-mini"><div class="stat-mini-value">${ca.cid||'--'}</div><div class="stat-mini-label">CID</div></div>
        </div>
        ${ca.angle_info ? `
        <div style="margin-top:10px;padding:8px;background:rgba(251,191,36,0.1);border-radius:6px;border:1px solid rgba(251,191,36,0.3);">
            <div style="color:#fbbf24;font-weight:700;font-size:0.9em;">🧭 زاوية القطاع المستخرجة: ${ca.angle_info.angle}° (${ca.angle_info.direction})</div>
            <div style="color:var(--text-muted);font-size:0.8em;margin-top:3px;">القطاع: ${ca.angle_info.sector_name} | الطريقة: ${ca.angle_info.method}</div>
            <div style="color:var(--text-muted);font-size:0.8em;margin-top:3px;">⚠️ الزاوية تُحسب داخل اتجاه قطاع الإشارة من البرج</div>
        </div>` : ''}
    `;

    // تحليل الإشارة
    const sa = data.signal_analysis;
    document.getElementById('signalAnalysis').innerHTML = `
        <div class="stats-row">
            <div class="stat-mini"><div class="stat-mini-value">${sa.signal_dbm} dBm</div><div class="stat-mini-label">الإشارة</div></div>
            <div class="stat-mini"><div class="stat-mini-value">${sa.estimated_distance.toFixed(0)}م</div><div class="stat-mini-label">المسافة</div></div>
        </div>
        <div style="margin-top:8px;font-size:0.85em;color:var(--text-muted);">
            <div>النموذج: ${sa.model_used}</div>
            <div>البيئة: ${sa.environment} | التردد: ${sa.freq_mhz} MHz</div>
        </div>
    `;

    // الأبراج الافتراضية
    let towersHtml = '';
    towersHtml += `
        <div class="tower-mini main-tower-mini">
            <h5>📡 البرج الأساسي</h5>
            <div class="tower-mini-row"><span>الإحداثيات</span><span class="tower-mini-value">${data.towers.main.lat}, ${data.towers.main.lon}</span></div>
            <div class="tower-mini-row"><span>اتجاه القطاع</span><span class="tower-mini-value">${data.towers.main.final_angle.toFixed(1)}°</span></div>
            <div class="tower-mini-row"><span>المسافة المقدرة</span><span class="tower-mini-value">${data.towers.main.estimated_distance.toFixed(0)} م</span></div>
        </div>
    `;
    data.towers.virtual.forEach((vt, i) => {
        towersHtml += `
            <div class="tower-mini">
                <h5>🤖 ${vt.label} (${vt.tower_id})</h5>
                <div class="tower-mini-row"><span>الإحداثيات</span><span class="tower-mini-value">${vt.lat}, ${vt.lon}</span></div>
                <div class="tower-mini-row"><span>الزاوية داخل القطاع</span><span class="tower-mini-value">${vt.angle}°</span></div>
                <div class="tower-mini-row"><span>المسافة من البرج</span><span class="tower-mini-value">${vt.distance_from_main.toFixed(1)} م</span></div>
                <div class="tower-mini-row"><span>قوة الإشارة</span><span class="tower-mini-value">${vt.signal_dbm} dBm</span></div>
            </div>
        `;
    });
    document.getElementById('towerList').innerHTML = towersHtml;

    // نتيجة التثليث
    const tri = data.triangulation;
    const confClass = tri.confidence >= 70 ? 'conf-high' : tri.confidence >= 40 ? 'conf-medium' : 'conf-low';
    const accBadge = tri.accuracy === 'high' ? 'badge-success' : tri.accuracy === 'medium' ? 'badge-warning' : 'badge-danger';
    const accText = tri.accuracy === 'high' ? 'عالية' : tri.accuracy === 'medium' ? 'متوسطة' : 'منخفضة';
    document.getElementById('triResult').innerHTML = `
        <div style="font-size:0.9em;margin-bottom:10px;">
            <div style="display:flex;justify-content:space-between;margin-bottom:5px;">
                <span style="color:var(--text-muted);">الطريقة</span>
                <span style="font-weight:700;">${tri.method}</span>
            </div>
            <div style="display:flex;justify-content:space-between;margin-bottom:5px;">
                <span style="color:var(--text-muted);">الأبراج المستخدمة</span>
                <span style="font-weight:700;">${tri.towers_used}</span>
            </div>
            <div style="display:flex;justify-content:space-between;margin-bottom:5px;">
                <span style="color:var(--text-muted);">مستوى الدقة</span>
                <span class="badge ${accBadge}">${accText}</span>
            </div>
        </div>
        <div style="display:flex;justify-content:space-between;margin-bottom:5px;font-size:0.9em;">
            <span>درجة الثقة</span>
            <span style="font-weight:700;">${tri.confidence}%</span>
        </div>
        <div class="confidence-bar">
            <div class="confidence-fill ${confClass}" style="width:${tri.confidence}%"></div>
        </div>
    `;

    // النتيجة النهائية
    const fr = data.final_result;
    document.getElementById('finalResult').innerHTML = `
        <div class="tower-mini phone-mini">
            <h5>📱 موقع الهاتف المقدر</h5>
            <div class="tower-mini-row"><span>خط العرض</span><span class="tower-mini-value">${fr.lat.toFixed(6)}</span></div>
            <div class="tower-mini-row"><span>خط الطول</span><span class="tower-mini-value">${fr.lon.toFixed(6)}</span></div>
            <div class="tower-mini-row"><span>المسافة من البرج</span><span class="tower-mini-value">${fr.distance_from_main.toFixed(0)} م</span></div>
            <div class="tower-mini-row"><span>الزاوية داخل القطاع</span><span class="tower-mini-value">${fr.angle.toFixed(1)}°</span></div>
        </div>
        <div class="coords-box">${fr.lat.toFixed(6)}, ${fr.lon.toFixed(6)}</div>
        <div style="font-size:0.8em;color:var(--text-muted);text-align:center;margin-top:8px;">
            ⚠️ النتيجة تقديرية وتعتمد على دقة المدخلات
        </div>
    `;
}

// الدالة الرئيسية
async function locate() {
    const loading = document.getElementById('loading');
    const results = document.getElementById('results');
    const errorMsg = document.getElementById('errorMsg');

    loading.classList.add('active');
    results.classList.remove('active');
    errorMsg.classList.remove('active');

    try {
        const res = await fetch('/api/locate', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
                cell_id: document.getElementById('cellId').value,
                lat: document.getElementById('lat').value,
                lon: document.getElementById('lon').value,
                direction: document.getElementById('direction').value,
                signal: document.getElementById('signal').value,
                environment: document.getElementById('environment').value,
                freq: document.getElementById('freq').value
            })
        });

        const data = await res.json();
        loading.classList.remove('active');

        if (data.status !== 'success') {
            errorMsg.textContent = '❌ ' + (data.message || 'خطأ غير معروف');
            errorMsg.classList.add('active');
            return;
        }

        // رسم على الخريطة
        drawOnMap(data);

        // عرض النتائج
        displayResults(data);

        results.classList.add('active');

    } catch (err) {
        loading.classList.remove('active');
        errorMsg.textContent = '❌ خطأ في الاتصال: ' + err.message;
        errorMsg.classList.add('active');
    }
}

// تهيئة الخريطة
window.onload = initMap;
</script>
'''


# ═══════════════════════════════════════════════════════════════
# Flask Routes - الزاوية داخل اتجاه قطاع الإشارة
# ═══════════════════════════════════════════════════════════════
@app.route('/')
def index():
    return render_template_string(HTML_TEMPLATE + JS_CODE)

@app.route('/api/locate', methods=['POST'])
def locate():
    try:
        data = request.get_json()

        # المدخلات
        cell_input = data.get('cell_id', '')
        main_lat = float(data.get('lat', 0))
        main_lon = float(data.get('lon', 0))
        user_direction = data.get('direction', 'auto')
        signal = float(data.get('signal', -80))
        environment = data.get('environment', 'urban')
        freq_mhz = float(data.get('freq', 900))

        # ═══════════════════════════════════════════════════
        # 1. تحليل Cell ID
        # ═══════════════════════════════════════════════════
        cell_analysis = CellIDAnalyzer.parse_cell_id(cell_input)

        # ═══════════════════════════════════════════════════
        # 2. استخراج زاوية القطاع من Cell ID
        # ═══════════════════════════════════════════════════
        extracted_sector_angle = None
        refined_angle = None
        refinement_note = ""
        angle_quality = 'low'

        if cell_analysis.get('angle_info'):
            extracted_sector_angle = cell_analysis['angle_info']['angle']

            if user_direction != 'auto' and user_direction != '':
                # المستخدم أدخل اتجاه قطاع الإشارة
                user_sector_angle = CellIDAnalyzer.DIRECTION_ANGLES.get(user_direction, None)

                if user_sector_angle is not None:
                    # حساب الزاوية داخل اتجاه القطاع
                    # الزاوية النهائية = زاوية القطاع من Cell ID + زاوية داخل القطاع
                    angle_diff = abs(user_sector_angle - extracted_sector_angle)
                    if angle_diff > 180:
                        angle_diff = 360 - angle_diff

                    if angle_diff <= 60:
                        # داخل نفس القطاع - استخدم زاوية داخل القطاع
                        refined_angle = extracted_sector_angle + (angle_diff / 2)
                        if refined_angle >= 360:
                            refined_angle -= 360
                        refinement_note = f"زاوية داخل القطاع: {extracted_sector_angle}° + {angle_diff/2}° = {refined_angle}°"
                        angle_quality = 'high'
                    elif angle_diff <= 90:
                        refined_angle = user_sector_angle
                        refinement_note = f"تصحيح جزئي: استخدام اتجاه القطاع المدخل ({user_sector_angle}°)"
                        angle_quality = 'medium'
                    else:
                        refined_angle = user_sector_angle
                        refinement_note = f"تعارض كبير: استخدام اتجاه القطاع المدخل ({user_sector_angle}°)"
                        angle_quality = 'low'
                else:
                    refined_angle = extracted_sector_angle
                    refinement_note = "زاوية القطاع من Cell ID"
                    angle_quality = 'medium'
            else:
                # استخراج تلقائي - استخدم زاوية القطاع كما هي
                refined_angle = extracted_sector_angle
                refinement_note = "زاوية القطاع مستخرجة تلقائياً من Cell ID"
                angle_quality = 'medium'
        else:
            if user_direction != 'auto' and user_direction != '':
                refined_angle = CellIDAnalyzer.DIRECTION_ANGLES.get(user_direction, 0)
                refinement_note = "زاوية القطاع من اتجاه المستخدم"
                angle_quality = 'low'
            else:
                refined_angle = 0
                refinement_note = "زاوية افتراضية 0°"
                angle_quality = 'low'

        final_angle = refined_angle if refined_angle is not None else 0

        # ═══════════════════════════════════════════════════
        # 3. تقدير المسافة
        # ═══════════════════════════════════════════════════
        main_distance = smart_distance_estimate(signal, freq_mhz, environment)

        # ═══════════════════════════════════════════════════
        # 4. توليد 3 أبراج افتراضية داخل اتجاه القطاع
        # ═══════════════════════════════════════════════════
        virtual_towers = TowerGenerator.generate_virtual_towers(
            main_lat, main_lon, main_distance, final_angle
        )

        # ═══════════════════════════════════════════════════
        # 5. التثليث
        # ═══════════════════════════════════════════════════
        all_towers = [{
            'lat': main_lat, 'lon': main_lon,
            'distance': main_distance,
            'weight': 1.0, 'source': 'main_user', 'tower_id': 'main'
        }]

        for vt in virtual_towers:
            all_towers.append({
                'lat': vt['lat'], 'lon': vt['lon'],
                'distance': main_distance,
                'weight': vt['weight'],
                'source': 'virtual',
                'tower_id': vt['tower_id']
            })

        if len(all_towers) >= 3:
            ls_result = least_squares_trilateration(all_towers)
            if ls_result:
                final_lat, final_lon = ls_result['lat'], ls_result['lon']
                method = 'Least Squares Trilateration'
            else:
                wc_result = weighted_centroid_trilateration(all_towers)
                if wc_result:
                    final_lat, final_lon = wc_result['lat'], wc_result['lon']
                    method = 'Weighted Centroid'
                else:
                    final_lat, final_lon = move(main_lat, main_lon, final_angle, main_distance)
                    method = 'Direction + Distance'
        else:
            final_lat, final_lon = move(main_lat, main_lon, final_angle, main_distance)
            method = 'Direction Only'

        # ═══════════════════════════════════════════════════
        # 6. حساب الثقة
        # ═══════════════════════════════════════════════════
        confidence = calculate_confidence(
            len(all_towers), signal, environment, angle_quality
        )

        accuracy = 'high' if len(all_towers) >= 4 and angle_quality in ['high', 'medium'] else                    'medium' if len(all_towers) >= 3 else 'low'

        # ═══════════════════════════════════════════════════
        # 7. إعداد الرد
        # ═══════════════════════════════════════════════════
        return jsonify({
            'status': 'success',
            'cell_analysis': {
                'provider': cell_analysis.get('provider', 'غير معروف'),
                'mcc': cell_analysis.get('mcc'),
                'mnc': cell_analysis.get('mnc'),
                'lac': cell_analysis.get('lac'),
                'cid': cell_analysis.get('cid'),
                'angle_info': cell_analysis.get('angle_info')
            },
            'signal_analysis': {
                'signal_dbm': signal,
                'estimated_distance': main_distance,
                'distance_min': main_distance * 0.5,
                'distance_max': main_distance * 1.5,
                'model_used': "COST-231 Hata" if freq_mhz >= 1500 else "Okumura-Hata",
                'environment': environment,
                'freq_mhz': int(freq_mhz)
            },
            'towers': {
                'main': {
                    'lat': main_lat,
                    'lon': main_lon,
                    'estimated_distance': main_distance,
                    'final_angle': final_angle
                },
                'virtual': virtual_towers
            },
            'triangulation': {
                'method': method,
                'towers_used': len(all_towers),
                'confidence': confidence,
                'accuracy': accuracy
            },
            'final_result': {
                'lat': final_lat,
                'lon': final_lon,
                'distance_from_main': haversine(main_lat, main_lon, final_lat, final_lon),
                'angle': final_angle
            }
        })

    except Exception as e:
        import traceback
        return jsonify({'status': 'error', 'message': str(e), 'trace': traceback.format_exc()}), 400

if __name__ == '__main__':
    print("=" * 60)
    print("🇱🇾 نظام تحديد المواقع الليبي - النسخة المُحسّنة")
    print("=" * 60)
    print("🌐 الواجهة تعمل على: http://localhost:9999")
    print("🗺️ خريطة قمر صناعي: Esri World Imagery + أسماء")
    print("📡 توليد 3 أبراج افتراضية داخل اتجاه القطاع")
    print("🧭 مؤشر بصري لاتجاه قطاع الإشارة")
    print("=" * 60)
    print("⏳ جاري تشغيل الخادم...")
    app.run(host='0.0.0.0', port=9999, debug=True)
