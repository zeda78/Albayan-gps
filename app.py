from flask import Flask, request, jsonify, render_template_string
import math
import os

app = Flask(__name__)

# قاعدة بيانات واقعية للأبراج (يمكنك إضافة وتعديل الـ CID والزاوية الفعلية هنا)
# الصيغة: 'CID': الزاوية بالدرجات
TOWERS_DATA = {
    '606-01-8256-12576': 180.0,  # البرج الحالي باتجاه الجنوب (180 درجة)
    '606-01-8256-12577': 0.0,    # قطاع آخر لنفس البرج باتجاه الشمال (0 درجة)
    '606-01-8256-12578': 90.0,   # قطاع باتجاه الشرق (90 درجة)
    '606-01-9999-11111': 225.0,  # برج افتراضي آخر باتجاه الجنوب الغربي
}

# معادلة حساب المسافة بناءً على المعايرة الميدانية (0.92)
def get_dist(sig): 
    return (10**(((61 - float(sig)) - 55) / 44.9) * 1000) * 0.92

@app.route('/')
def home():
    return render_template_string('''
    <!DOCTYPE html><html dir="rtl"><head><meta name="viewport" content="width=device-width, initial-scale=1.0"><link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/><script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
    <style>
        body{background:#0f172a;color:#fff;font-family:sans-serif;margin:0;padding:10px}
        .card{background:#1e293b;padding:15px;border-radius:12px;margin-bottom:10px}
        input,button{width:100%;padding:12px;margin:5px 0;border-radius:8px;border:1px solid #334155;background:#0f172a;color:#fff;font-size:16px;box-sizing:border-box;}
        #map{height:350px;width:100%;border-radius:10px;margin:10px 0}
        .info-box{background:#334155;padding:10px;border-radius:8px;margin-top:5px;font-size:14px;color:#cbd5e1}
    </style></head><body>
    <div class="card"><h3>نظام تحديد المواقع الليبي الذكي (ربط تلقائي بالبرج)</h3>
    
    <label>معرف البرج (CID):</label>
    <input type="text" id="cid" value="606-01-8256-12576">
    
    <label>خط العرض الحالي (Latitude):</label>
    <input type="number" id="lat" value="32.854287" step="any">
    
    <label>خط الطول الحالي (Longitude):</label>
    <input type="number" id="lon" value="13.236523" step="any">
    
    <button onclick="loc()" style="background:#2563eb;font-weight:bold;border:none;cursor:pointer;margin-top:10px;">🎯 تحديد الموقع التلقائي</button>
    
    <div id="info" class="info-box" style="display:none;"></div>
    <div id="map"></div>
    <div id="res"></div>
    </div>
    
    <script>
        var map = L.map('map').setView([32.854287, 13.236523], 15);
        L.tileLayer('https://{s}.google.com/vt/lyrs=s,h&x={x}&y={y}&z={z}', {subdomains:['mt0','mt1','mt2','mt3']}).addTo(map);
        var lyr = L.layerGroup().addTo(map);
        
        function loc(){
            fetch('/calc', {
                method:'POST', 
                headers:{'Content-Type':'application/json'}, 
                body:JSON.stringify({
                    cid:document.getElementById('cid').value, 
                    lat:document.getElementById('lat').value, 
                    lon:document.getElementById('lon').value
                })
            })
            .then(r=>r.json()).then(d=>{
                lyr.clearLayers();
                
                // عرض بيانات الاتجاه المستخرجة من السيرفر
                var infoDiv = document.getElementById('info');
                infoDiv.style.display = 'block';
                infoDiv.innerHTML = `📡 <b>اتجاه البرج المكتشف:</b> ${d.bearing}° (${d.direction_name})`;
                
                // رسم النقطة والدائرة
                L.marker([d.lat, d.lon]).addTo(lyr).bindPopup(`الموقع المحسوب بناءً على اتجاه البرج (${d.bearing}°)`).openPopup();
                L.circle([d.lat, d.lon], {radius:250, color:'#10b981', fillOpacity:0.2}).addTo(lyr);
                map.setView([d.lat, d.lon], 16);
                
                // زر خرائط جوجل المصحح والمحدث بالكامل
                document.getElementById('res').innerHTML = `<a href="https://www.google.com/maps/search/?api=1&query=${d.lat},${d.lon}" target="_blank" style="display:block;padding:15px;background:#10b981;text-align:center;color:white;text-decoration:none;border-radius:8px;font-weight:bold;margin-top:10px;">🗺️ فتح في خرائط جوجل</a>`;
            });
        }
    </script></body></html>''')

@app.route('/calc', methods=['POST'])
def calc():
    d = request.json
    lat, lon = float(d['lat']), float(d['lon'])
    cid = d.get('cid', '').strip()
    
    # البحث عن زاوية البرج في قاعدة البيانات، وإذا لم يجدها يضع 180 (جنوب) كافتراضي
    bearing = TOWERS_DATA.get(cid, 180.0)
    
    # تحديد اسم الاتجاه للعرض فقط
    direction_name = "جنوب"
    if bearing == 0.0: direction_name = "شمال"
    elif bearing == 90.0: direction_name = "شرق"
    elif bearing == 270.0: direction_name = "غرب"
    elif 0 < bearing < 90: direction_name = "شمال شرقي"
    elif 90 < bearing < 180: direction_name = "جنوب شرقي"
    elif 180 < bearing < 270: direction_name = "جنوب غربي"
    elif 270 < bearing < 360: direction_name = "شمال غربي"

    # حساب المسافة بناءً على المعايرة الميدانية
    dist = get_dist(-80) 
    bearing_rad = math.radians(bearing)
    
    # حساب الإزاحة الجغرافية الدقيقة بزاوية 360 درجة
    nlat = lat + (dist / 111000) * math.cos(bearing_rad)
    nlon = lon + (dist / (111000 * math.cos(math.radians(lat)))) * math.sin(bearing_rad)
    
    return jsonify({
        'lat': round(nlat, 6), 
        'lon': round(nlon, 6),
        'bearing': bearing,
        'direction_name': direction_name
    })

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
