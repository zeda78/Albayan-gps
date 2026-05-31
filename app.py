from flask import Flask, request, jsonify, render_template_string
import math

app = Flask(__name__)

# ═══════════════════════════════════════════════════════════════
# توليد الأبراج الافتراضية - 3 أبراج فقط داخل نطاق القطاع
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
# واجهة العرض HTML المحدثة مع دمج الشعار كخلفية ممتدة كاملة
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
            --bg: #0f172a; --card: rgba(30, 41, 59, 0.85); --border: #334155;
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
        
        /* تأثير الشعار كخلفية كاملة ممتدة وعلامة مائية ثابتة */
        body::before {
            content: "";
            position: absolute;
            top: 0; left: 0; right: 0; bottom: 0;
            background-image: url('https://images.gemini.googleusercontent.com/api/view?docid=F0_M342mB_7T9eM');
            background-repeat: no-repeat;
            background-position: center;
            background-size: 45%; /* حجم الشعار المتمركز في الخلفية */
            opacity: 0.05; /* درجة الشفافية الخفيفة لعدم التشويش على البيانات */
            z-index: -1;
            pointer-events: none;
        }

        .container { max-width: 100%; height: 100vh; display: flex; flex-direction: column; padding: 10px; gap: 10px; position: relative; z-index: 1; }
        .header { background: var(--card); padding: 12px 20px; border-radius: 12px; border: 1px solid var(--border); display: flex; justify-content: space-between; align-items: center; backdrop-filter: blur(8px); }
        .header h1 { font-size: 1.4em; font-weight: 800; background: linear-gradient(135deg, #3b82f6, #10b981); -webkit-background-clip: text; -webkit-text-fill-color: transparent; }
        .grid { display: flex; flex: 1; gap: 10px; min-height: 0; }
        .sidebar { width: 380px; display: flex; flex-direction: column; gap: 10px; overflow-y: auto; padding-right: 2px; }
        .sidebar::-webkit-scrollbar { width: 5px; }
        .sidebar::-webkit-scrollbar-thumb { background: var(--border); border-radius: 3px; }
        .card { background: var(--card); border-radius: 12px; padding: 15px; border: 1px solid var(--border); backdrop-filter: blur(8px); }
        .card-title { font-size: 0.95em; font-weight: 700; color: #60a5fa; margin-bottom: 12px; padding-bottom: 6px; border-bottom: 1px solid var(--border); display: flex; align-items: center; gap: 6px; }
        .form-group { margin-bottom: 10px; }
        .form-group label { display: block; font-weight: 600; margin-bottom: 4px; color: var(--text-muted); font-size: 0.85em; }
        input, select { width: 100%; padding: 8px 12px; border-radius: 6px; border: 1px solid var(--border); background: rgba(15, 23, 42, 0.8); color: var(--text); font-family: 'Cairo'; font-size: 0.9em; }
        .btn { width: 100%; padding: 10px; border-radius: 8px; border: none; font-family: 'Cairo'; font-size: 0.95em; font-weight: 700; cursor: pointer; transition: all 0.2s; background: linear-gradient(135deg, var(--primary), var(--primary-dark)); color: white; }
        .btn:hover { opacity: 0.9; transform: translateY(-1px); }
        .map-container { flex: 1; background: var(--card); border-radius: 12px; border: 1px solid var(--border); overflow: hidden; position: relative; backdrop-filter: blur(8px); }
        #map { height: 100%; width: 100%; }
        .map-legend { position: absolute; bottom: 20px; left: 20px; background: rgba(15, 23, 42, 0.9); padding: 12px; border-radius: 8px; border: 1px solid var(--border); z-index: 1000; font-size: 0.8em; backdrop-filter: blur(5px); }
        .legend-item { display: flex; align-items: center; gap: 8px; margin: 5px 0; }
        .legend-icon { width: 12px; height: 12px; border-radius: 50%; }
        .result-section { display: none; flex-direction: column; gap: 10px; }
        .result-section.active { display: flex; }
        .
