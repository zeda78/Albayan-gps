from flask import Flask, request, jsonify, render_template_string, send_from_directory
import math
import os

app = Flask(__name__)

# تحديد المجلد الرئيسي للمشروع بشكل ديناميكي لضمان الوصول للملفات
BASE_DIR = os.path.abspath(os.path.dirname(__file__))

# الدالة البرمجية المسؤولة عن تمرير الشعار للمتصفح بأمان وبدون 404
@app.route('/logo.jpg')
def serve_logo():
    return send_from_directory(BASE_DIR, 'logo.jpg')

# ═══════════════════════════════════════════════════════════════
# خوارزميات التثليث الراديوي والحسابات الجغرافية
# ═══════════════════════════════════════════════════════════════
class TowerGenerator:
    @staticmethod
    def generate_virtual_towers(main_lat, main_lon, main_distance, final_angle):
        towers = []
        angles = [final_angle - 45, final_angle, final_angle + 45]
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
                        if result['mnc'] == 0: result['provider'] = 'Libyana'
                        elif result['mnc'] == 1: result['provider'] = 'Al-Madar'
                    result['angle_info'] = CellIDAnalyzer.extract_angle_from_cid(result['cid'], result['provider'])
                except:
                    pass
        return result

    @staticmethod
    def extract_angle_from_cid(cid, provider):
        provider_key = 'libyana' if 'libyana' in provider.lower() else 'almadar'
        patterns = CellIDAnalyzer.SECTOR_PATTERNS.get(provider_key, CellIDAnalyzer.SECTOR_PATTERNS['almadar'])
        sector_id = cid % 3 if provider_key == 'libyana' else cid % 6
        angle_data = patterns.get(sector_id, {'angle': 0, 'direction': 'شمال', 'sector': 'Unknown'})
        return {
            'sector_id': sector_id, 'angle': angle_data['angle'], 'direction': angle_data['direction'],
            'sector_name': angle_data['sector'], 'method': f'CID mod {3 if provider_key == "libyana" else 6}'
        }

    @staticmethod
    def refine_angle(user_direction, extracted_angle_info):
        if not extracted_angle_info: return None, "لا يوجد زاوية مستخرجة"
        user_angle = CellIDAnalyzer.DIRECTION_ANGLES.get(user_direction, None)
        if user_angle is None: return extracted_angle_info['angle'], "زاوية مستخرجة فقط"
        extracted_angle = extracted_angle_info['angle']
        angle_diff = abs(user_angle - extracted_angle)
        if angle_diff > 180: angle_diff = 360 - angle_diff
        if angle_diff <= 30:
            return (user_angle + extracted_angle) / 2, f"تطابق عالي (فرق {angle_diff}°)"
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

def weighted_centroid_trilateration(towers):
    if len(towers) < 2: return None
    total_weight = 0
    weighted_lat, weighted_lon = 0, 0
    for t in towers:
        weight = t.get('weight', 1.0) / max(t['distance_from_main'], 50)
        weighted_lat += t['lat'] * weight
        weighted_lon += t['lon'] * weight
        total_weight += weight
    if total_weight == 0: return None
    return {'lat': weighted_lat / total_weight, 'lon': weighted_lon / total_weight}

def calculate_confidence(towers_used, signal_quality, environment, angle_quality):
    score = 25 if towers_used >= 3 else 15
    if signal_quality >= -70: score += 25
    elif signal_quality >= -85: score += 20
    elif signal_quality >= -100: score += 12
    else: score += 5
    env_scores = {'rural': 15, 'suburban': 12, 'urban': 8, 'indoor': 3}
    score += env_scores.get(environment, 8)
    if "تطابق عالي" in angle_quality: score += 25
    elif "تصحيح" in angle_quality: score += 15
    else: score += 5
    return min(score, 100)

# ═══════════════════════════════════════════════════════════════
# واجهة العرض HTML المحدثة للتكامل مع شعار logo.jpg الأصلي
# ═══════════════════════════════════════════════════════════════
HTML_TEMPLATE = '''
<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>نظام التحليل الجغرافي - منظومة البيان</title>
    <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
    <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Cairo:wght@400;600;700;800&display=swap');
        * { margin: 0; padding: 0; box-sizing: border-box; }
        :root {
            --primary: #2563eb; --primary-dark: #1d4ed8; --success: #10b981;
            --warning: #f59e0b; --danger: #ef4444; --info: #06b6d4;
            --virtual: #8b5cf6; --main: #f97316; --phone: #ec4899;
            --bg: #0f172a; --card: rgba(30, 41, 59, 0.88); --border: #334155;
            --text: #f1f5f9; --text-muted: #94a3b8;
        }
        body { 
            background-color: var(--bg); 
            color: var(--text); 
            font-family: 'Cairo', sans-serif; 
            min-height: 100vh; 
            overflow: hidden;
            position: relative;
        }
        
        /* طبقة مخصصة لعرض الشعار المائي بدقة وبدون حواف بيضاء مكسورة */
        .watermark-overlay {
            position: absolute;
            top: 50%;
            left: 50%;
            transform: translate(-50%, -50%);
            width: 480px;
            height: 480px;
            background-image: url('/logo.jpg');
            background-repeat: no-repeat;
            background-position: center;
            background-size: contain;
            opacity: 0.12;
            z-index: 1;
            pointer-events: none;
            mix-blend-mode: initial; /* الحفاظ على تباين الألوان الداكنة للشعار */
        }

        .container { max-width: 100%; height: 100vh; display: flex; flex-direction: column; padding: 10px; gap: 10px; position: relative; z-index: 2; }
        .header { background: var(--card); padding: 12px 20px; border-radius: 12px; border: 1px solid var(--border); display: flex; justify-content: space-between; align-items: center; backdrop-filter: blur(8px); }
        .header h1 { font-size: 1.4em; font-weight: 800; background: linear-gradient(135deg, #3b82f6, #10b981); -webkit-background-clip: text; -webkit-text-fill-color: transparent; }
        .grid { display: flex; flex: 1; gap: 10px; min-height: 0; }
        .sidebar { width: 380px; display: flex; flex-direction: column; gap: 10px; overflow-y: auto; padding-right: 2px; position: relative; z-index: 5; }
        .sidebar::-webkit-scrollbar { width: 5px; }
        .sidebar::-webkit-scrollbar-thumb { background: var(--border); border-radius: 3px; }
        .card { background: var(--card); border-radius: 12px; padding: 15px; border: 1px solid var(--border); backdrop-filter: blur(8px); }
        .card-title { font-size: 0.95em; font-weight: 700; color: #60a5fa; margin-bottom: 12px; padding-bottom: 6px; border-bottom: 1px solid var(--border); display: flex; align-items: center; gap: 6px; }
        .form-group { margin-bottom: 10px; }
        .form-group label { display: block; font-weight: 600; margin-bottom: 4px; color: var(--text-muted); font-size: 0.85em; }
        input, select { width: 100%; padding: 8px 12px; border-radius: 6px; border: 1px solid var(--border); background: rgba(15, 23, 42, 0.8); color: var(--text); font-family: 'Cairo'; font-size: 0.9em; }
        .btn { width: 100%; padding: 10px; border-radius: 8px; border: none; font-family: 'Cairo'; font-size: 0.95em; font-weight: 700; cursor: pointer; transition: all 0.2s; background: linear-gradient(135deg, var(--primary), var(--primary-dark)); color: white; }
        .btn:hover { opacity: 0.9; transform: translateY(-1px); }
        .map-container { flex: 1; background: var(--card); border-radius: 12px; border: 1px solid var(--border); overflow: hidden; position: relative; backdrop-filter: blur(8px); z-index: 4; }
        #map { height: 100%; width: 100%; }
        .map-legend { position: absolute; bottom: 20px; left: 20px; background: rgba(15, 23, 42, 0.9); padding: 12px; border-radius: 8px; border: 1px solid var(--border); z-index: 1000; font-size: 0.8em; backdrop-filter: blur(5px); }
        .legend-item { display: flex; align-items: center; gap: 8px; margin: 5px 0; }
        .legend-icon { width: 12px; height: 12px; border-radius: 50%; }
        .result-section { display: none; flex-direction: column; gap: 10px; }
        .result-section.active { display: flex; }
        .mini-row { display: flex; justify-content: space-between; font-size: 0.85em; padding: 3px 0; border-bottom: 1px dashed rgba(255,255,255,0.05); }
        .mini-label { color: var(--text-muted); }
        .mini-value { color: #f1f5f9; font-weight: 600; direction: ltr; }
        .confidence-container { margin-top: 8px; }
        .confidence-bar { width: 100%; height: 6px; background: rgba(0,0,0,0.3); border-radius: 3px; overflow: hidden; margin-top: 4px; }
        .confidence-fill { height: 100%; width: 0%; transition: width 0.5s ease; }
        .loading { display: none; text-align: center; padding: 20px; color: var(--info); font-size: 0.9em; }
        .loading.active { display: block; }
    </style>
</head>
<body>
<div class="watermark-overlay"></div>
<div class="container">
    <div class="header">
        <h1>📊 نظام تتبع وتحليل قطاعات الإشارة - منظومة البيان</h1>
        <div style="font-size: 0.85em; color: var(--text-muted);">مديرية أمن طرابلس - وزارة الداخلية</div>
    </div>
    <div class="grid">
        <div class="sidebar">
            <div class="card">
                <div class="card-title">📡 مدخلات المحطة والخلية</div>
                <div class="form-group">
                    <label>معرف الخلية الرئيسي (Cell ID)</label>
                    <input type="text" id="cellId" value="606-01-1021-8973">
                </div>
                <div class="form-group" style="display: grid; grid-template-columns: 1fr 1fr; gap: 8px;">
                    <div>
                        <label>خط العرض (Lat)</label>
                        <input type="number" id="lat" step="any" value="32.853826">
                    </div>
                    <div>
                        <label>خط الطول (Lon)</label>
                        <input type="number" id="lon" step="any" value="13.241509">
                    </div>
                </div>
                <div class="form-group">
                    <label>الاتجاه الجغرافي المقدر</label>
                    <select id="direction">
                        <option value="auto">🔍 استخراج تلقائي مبني على الخوارزمية</option>
                        <option value="شمال">شمال (0°)</option>
                        <option value="شمال شرق">شمال شرق (45°)</option>
                        <option value="شرق">شرق (90°)</option>
                        <option value="جنوب شرق">جنوب شرق (135°)</option>
                        <option value="جنوب">جنوب (180°)</option>
                        <option value="جنوب غرب">جنوب غرب (225°)</option>
                        <option value="غرب">غرب (270°)</option>
                        <option value="شمال غرب">شمال غرب (315°)</option>
                    </select>
                </div>
                <div class="form-group" style="display: grid; grid-template-columns: 1fr 1fr; gap: 8px;">
                    <div>
                        <label>مستوى خسارة الإشارة</label>
                        <select id="signal">
                            <option value="-60">قوية (-60 dBm)</option>
                            <option value="-78" selected>متوسطة (-78 dBm)</option>
                            <option value="-95">ضعيفة (-95 dBm)</option>
                            <option value="-110">ميتة (-110 dBm)</option>
                        </select>
                    </div>
                    <div>
                        <label>التردد الراديوي</label>
                        <select id="freq">
                            <option value="900" selected>900 MHz (GSM)</option>
                            <option value="1800">1800 MHz (DCS)</option>
                            <option value="2100">2100 MHz (3G)</option>
                        </select>
                    </div>
                </div>
                <div class="form-group">
                    <label>الطبيعة الطبوغرافية (البيئة)</label>
                    <select id="environment">
                        <option value="urban" selected>مدنية مزدحمة (Urban)</option>
                        <option value="suburban">ضواحي مفتوحة (Suburban)</option>
                        <option value="rural">شبه صحراوية / ريفية (Rural)</option>
                    </select>
                </div>
                <button class="btn" onclick="executeAnalysis()">🎯 إسقاط وبدء الحساب الجغرافي</button>
            </div>

            <div class="loading" id="loader">⏳ جاري موازنة مصفوفة التثليث الراديوي...</div>

            <div class="result-section" id="resultsBox">
                <div class="card">
                    <div class="card-title">🔍 تفكيك وتحليل تفاصيل الخلية</div>
                    <div id="cellDetails"></div>
                </div>
                <div class="card">
                    <div class="card-title">🎯 تقدير المسافة الجغرافية والموثوقية</div>
                    <div id="distanceDetails"></div>
                </div>
            </div>
        </div>
        <div class="map-container">
            <div id="map"></div>
            <div class="map-legend">
                <div style="font-weight: bold; margin-bottom: 5px; color:#60a5fa;">مفتاح الرموز الجغرافية</div>
                <div class="legend-item"><div class="legend-icon" style="background:#f97316;"></div><span>البرج المستهدف الأساسي</span></div>
                <div class="legend-item"><div class="legend-icon" style="background:#8b5cf6;"></div><span>نقاط التثليث الافتراضية</span></div>
                <div class="legend-item"><div class="legend-icon" style="background:#ef4444;"></div><span>دائرة التمركز بقطر 40 متر</span></div>
                <div class="legend-item"><div class="legend-icon" style="background:#ec4899;"></div><span>المنطقة المحتملة لتواجد الهدف</span></div>
            </div>
        </div>
    </div>
</div>

<script>
let map, markers = [], layers = [];

function initMap() {
    map = L.map('map', { center: [32.8538, 13.2415], zoom: 12, attributionControl: false });
    L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}', { maxZoom: 19 }).addTo(map);
    L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/Reference/World_Boundaries_and_Places/MapServer/tile/{z}/{y}/{x}', { maxZoom: 19 }).addTo(map);
}

function cleanCanvas() {
    markers.forEach(m => map.removeLayer(m));
    layers.forEach(l => map.removeLayer(l));
    markers = []; layers = [];
}

function drawVisualSector(lat, lon, angle, radius) {
    let angleRad = (angle * Math.PI) / 180;
    let endLat = lat + (radius / 111320) * Math.cos(angleRad);
    let endLon = lon + (radius / (111320 * Math.cos((lat * Math.PI) / 180))) * Math.sin(angleRad);
    
    let centerLine = L.polyline([[lat, lon], [endLat, endLon]], { color: '#fbbf24', weight: 4, opacity: 0.95 }).addTo(map);
    layers.push(centerLine);

    let focusCircle = L.circle([endLat, endLon], {
        radius: 20, 
        color: '#ef4444',
        fillColor: '#ef4444',
        fillOpacity: 0.4,
        weight: 2
    }).addTo(map).bindPopup('<b>بؤرة الفحص الميداني المقدرة (القطر: 40 متر)</b>');
    layers.push(focusCircle);

    let points = [[lat, lon]];
    let startAngle = angle - 60;
    let endAngle = angle + 60;
    for(let i = startAngle; i <= endAngle; i += 5) {
        let r = (i * Math.PI) / 180;
        let pLat = lat + (radius / 111320) * Math.cos(r);
        let pLon = lon + (radius / (111320 * Math.cos((lat * Math.PI) / 180))) * Math.sin(r);
        points.push([pLat, pLon]);
    }
    points.push([lat, lon]);
    let arcArea = L.polygon(points, { color: '#fbbf24', fillColor: '#fbbf24', fillOpacity: 0.1, weight: 1, dashArray: '4,4' }).addTo(map);
    layers.push(arcArea);
}

function executeAnalysis() {
    document.getElementById('loader').classList.add('active');
    let payload = {
        cell_id: document.getElementById('cellId').value,
        lat: parseFloat(document.getElementById('lat').value),
        lon: parseFloat(document.getElementById('lon').value),
        direction: document.getElementById('direction').value,
        signal: parseInt(document.getElementById('signal').value),
        freq: parseInt(document.getElementById('freq').value),
        environment: document.getElementById('environment').value
    };

    fetch('/api/analyze', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
    })
    .then(res => res.json())
    .then(data => {
        document.getElementById('loader').classList.remove('active');
        if(data.status === 'success') {
            renderInterfaceData(data);
            plotGeographicalData(data.result);
        }
    });
}

function renderInterfaceData(data) {
    document.getElementById('resultsBox').classList.add('active');
    let cellHtml = `
        <div class="mini-row"><span class="mini-label">المشغل المحلي</span><span class="mini-value" style="color:#60a5fa">${data.result.cell_info.provider}</span></div>
        <div class="mini-row"><span class="mini-label">الرمز الدولي (MCC-MNC)</span><span class="mini-value">${data.result.cell_info.mcc} - ${data.result.cell_info.mnc}</span></div>
        <div class="mini-row"><span class="mini-label">موقع الرمز (LAC-CID)</span><span class="mini-value">${data.result.cell_info.lac} - ${data.result.cell_info.cid}</span></div>
        <div class="mini-row"><span class="mini-label">الزاوية المستخرجة</span><span class="mini-value">${data.result.towers.main.extracted_angle}°</span></div>
    `;
    document.getElementById('cellDetails').innerHTML = cellHtml;

    let distanceHtml = `
        <div class="mini-row"><span class="mini-label">مسافة البحث الافتراضية</span><span class="mini-value">${data.result.towers.main.estimated_distance.toFixed(1)} م</span></div>
        <div class="mini-row"><span class="mini-label">بؤرة المعاينة الميدانية</span><span class="mini-value" style="color:#ef4444">دائرة قطرها 40 متر ثابتة</span></div>
        <div class="confidence-container">
            <div class="mini-row"><span class="mini-label">درجة الدقة والموثوقية الجغرافية</span><span class="mini-value" style="color:#10b981">${data.result.confidence}%</span></div>
            <div class="confidence-bar"><div class="confidence-fill" style="width:${data.result.confidence}%; background:#10b981"></div></div>
        </div>
    `;
    document.getElementById('distanceDetails').innerHTML = distanceHtml;
}

function plotGeographicalData(res) {
    cleanCanvas();
    let main = res.towers.main;
    
    drawVisualSector(main.lat, main.lon, main.final_angle, main.estimated_distance);

    let mainMarker = L.marker([main.lat, main.lon], {
        icon: L.divIcon({ html: `<div style="background:#f97316; width:16px; height:16px; border-radius:50%; border:2px solid #fff; box-shadow:0 0 10px #f97316;"></div>`, className: '' })
    }).addTo(map);
    markers.push(mainMarker);

    res.towers.virtual.forEach(vt => {
        let vtM = L.marker([vt.lat, vt.lon], {
            icon: L.divIcon({ html: `<div style="background:#8b5cf6; width:12px; height:12px; border-radius:50%; border:2px solid #fff;"></div>`, className: '' })
        }).addTo(map);
        markers.push(vtM);
    });

    let final = res.final_result;
    let phoneMarker = L.marker([final.lat, final.lon], {
        icon: L.divIcon({ html: `<div style="background:#ec4899; width:18px; height:18px; border-radius:50%; border:3px solid #fff; box-shadow:0 0 12px #ec4899;"></div>`, className: '' })
    }).addTo(map).bindPopup('<b>الموقع النهائي بعد التثليث الموزون</b>');
    markers.push(phoneMarker);

    let group = new L.featureGroup(markers);
    map.fitBounds(group.getBounds().pad(0.3));
}

window.onload = initMap;
</script>
</body>
</html>
'''

@app.route('/')
def home():
    return render_template_string(HTML_TEMPLATE)

@app.route('/api/analyze', methods=['POST'])
def api_analyze():
    data = request.get_json() or {}
    cell_id_raw = data.get('cell_id', '')
    main_lat = float(data.get('lat', 32.853826))
    main_lon = float(data.get('lon', 13.241509))
    user_direction = data.get('direction', 'auto')
    rssi = int(data.get('signal', -75))
    freq = int(data.get('freq', 900))
    env = data.get('environment', 'urban')

    cell_analysis = CellIDAnalyzer.parse_cell_id(cell_id_raw)
    ext_angle = cell_analysis['angle_info']['angle'] if cell_analysis['angle_info'] else 0
    ext_dir = cell_analysis['angle_info']['direction'] if cell_analysis['angle_info'] else "شمال"
    
    if user_direction == "auto":
        final_angle = ext_angle
        refinement_status = "استخراج آلي كامل من خوارزمية السيكتور"
    else:
        final_angle, refinement_status = CellIDAnalyzer.refine_angle(user_direction, cell_analysis['angle_info'])

    est_distance = smart_distance_estimate(rssi, freq_mhz=freq, environment=env)
    virtual_towers = TowerGenerator.generate_virtual_towers(main_lat, main_lon, est_distance, final_angle)

    towers_for_tri = [{'lat': main_lat, 'lon': main_lon, 'distance': est_distance, 'weight': 1.0}]
    for vt in virtual_towers:
        towers_for_tri.append({
            'lat': vt['lat'], 'lon': vt['lon'], 'distance': vt['distance_from_main'] * 0.5, 'weight': vt['weight']
        })
    
    final_coords = weighted_centroid_trilateration(towers_for_tri)
    confidence = calculate_confidence(len(virtual_towers), rssi, env, refinement_status)

    response_payload = {
        'status': 'success',
        'result': {
            'cell_info': cell_analysis,
            'confidence': confidence,
            'towers': {
                'main': {
                    'lat': main_lat, 'lon': main_lon, 'estimated_distance': est_distance,
                    'extracted_angle': ext_angle, 'extracted_direction': ext_dir,
                    'final_angle': final_angle, 'refinement': refinement_status
                },
                'virtual': virtual_towers
            },
            'final_result': {
                'lat': round(final_coords['lat'], 6) if final_coords else main_lat,
                'lon': round(final_coords['lon'], 6) if final_coords else main_lon,
                'distance_from_main': round(haversine(main_lat, main_lon, final_coords['lat'], final_coords['lon']), 1) if final_coords else 0
            }
        }
    }
    return jsonify(response_payload)

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
