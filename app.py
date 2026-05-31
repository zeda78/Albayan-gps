from flask import Flask, request, jsonify, render_template_string
import math
import os

app = Flask(__name__)

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
        input,select,button{width:100%;padding:12px;margin:5px 0;border-radius:8px;border:1px solid #334155;background:#0f172a;color:#fff;font-size:16px;box-sizing:border-box;}
        #map{height:350px;width:100%;border-radius:10px;margin:10px 0}
    </style></head><body>
    <div class="card"><h3>نظام تحديد المواقع الليبي للمسافات البعيدة</h3>
    <label>معرف البرج (CID):</label>
    <input type="text" id="cid" value="606-01-8256-12576">
    
    <label>خط العرض الحالي (Latitude):</label>
    <input type="number" id="lat" value="32.854287" step="any">
    
    <label>خط الطول الحالي (Longitude):</label>
    <input type="number" id="lon" value="13.236523" step="any">
    
    <label>اتجاه المسار المرصود (الزاوية):</label>
    <select id="bearing">
        <option value="0">⬆️ شمال (0°)</option>
        <option value="45">↗️ شمال شرقي (45°)</option>
        <option value="90">➡️ شرق (90°)</option>
        <option value="135">↘️ جنوب شرقي (135°)</option>
        <option value="180" selected>⬇️ جنوب (180°)</option>
        <option value="225">↙️ جنوب غربي (225°)</option>
        <option value="270">⬅️ غرب (270°)</option>
        <option value="315">↖️ شمال غربي (315°)</option>
    </select>
    
    <button onclick="loc()" style="background:#2563eb;font-weight:bold;border:none;cursor:pointer;margin-top:10px;">🎯 حساب نقطة الهدف</button>
    <div id="map"></div><div id="res"></div></div>
    <script>
        var map = L.map('map').setView([32.854287, 13.236523], 10);
        L.tileLayer('https://{s}.google.com/vt/lyrs=s,h&x={x}&y={y}&z={z}', {subdomains:['mt0','mt1','mt2','mt3']}).addTo(map);
        var lyr = L.layerGroup().addTo(map);
        
        function loc(){
            fetch('/calc', {
                method:'POST', 
                headers:{'Content-Type':'application/json'}, 
                body:JSON.stringify({
                    cid:document.getElementById('cid').value, 
                    lat:document.getElementById('lat').value, 
                    lon:document.getElementById('lon').value,
                    bearing:document.getElementById('bearing').value
                })
            })
            .then(r=>r.json()).then(d=>{
                lyr.clearLayers();
                L.marker([d.lat, d.lon]).addTo(lyr).bindPopup("الهدف المحسوب").openPopup();
                L.circle([d.lat, d.lon], {radius:1000, color:'red', fillOpacity:0.15}).addTo(lyr);
                map.setView([d.lat, d.lon], 11);
                // تم تصحيح علامة اللترال هنا لتصبح مدعومة بشكل صحيح في خرائط جوجل
                document.getElementById('res').innerHTML = `<a href="https://www.google.com/maps/search/?api=1&query=${d.lat},${d.lon}" target="_blank" style="display:block;padding:15px;background:#10b981;text-align:center;color:white;text-decoration:none;border-radius:8px;font-weight:bold;">🗺️ فتح النقطة في خرائط جوجل</a>`;
            });
        }
    </script></body></html>''')

@app.route('/calc', methods=['POST'])
def calc():
    d = request.json
    lat1 = math.radians(float(d['lat']))
    lon1 = math.radians(float(d['lon']))
    bearing = math.radians(float(d.get('bearing', 180)))
    
    # حساب المسافة بالكيلومتر وتحويلها لنسبة من نصف قطر الأرض
    dist = get_dist(-80) / 1000.0 
    R = 6371.0 # نصف قطر الكرة الأرضية بالكيلومترات
    
    # معادلة الملاحة الكروية المتقدمة لحساب الإحداثيات الجديدة بدقة
    lat2 = math.asin(math.sin(lat1) * math.cos(dist/R) + math.cos(lat1) * math.sin(dist/R) * math.cos(bearing))
    lon2 = lon1 + math.atan2(math.sin(bearing) * math.sin(dist/R) * math.cos(lat1), math.cos(dist/R) - math.sin(lat1) * math.sin(lat2))
    
    return jsonify({
        'lat': round(math.degrees(lat2), 6), 
        'lon': round(math.degrees(lon2), 6)
    })

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
