from flask import Flask, render_template, request, redirect, url_for

app = Flask(__name__)

# Sample location data
locations = {\n    'Location 1': {'lat': 35.6895, 'lon': 139.6917},\n    'Location 2': {'lat': 34.0522, 'lon': -118.2437},\n    'Location 3': {'lat': 51.5074, 'lon': -0.1278},\n}

# Store reports
reports = []

@app.route('/')
def home():
    return render_template('index.html', locations=locations.keys(), reports=reports)

@app.route('/add_report', methods=['POST'])
def add_report():
    report_type = request.form.get('report_type')
    location = request.form.get('location')
    price = float(request.form.get('price'))
    lat = locations[location]['lat']
    lon = locations[location]['lon']
    reports.append({'type': report_type, 'location': location, 'lat': lat, 'lon': lon, 'price': price})
    return redirect(url_for('home'))

@app.route('/total_price')
def total_price():
    total = sum(report['price'] for report in reports)
    return {'total': total}

if __name__ == '__main__':
    app.run(debug=True)