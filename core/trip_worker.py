import fpdf

class TripPlannerReport:
    def __init__(self, location, vehicle_details, fuel_consumption, route_info, accommodations):
        self.location = location
        self.vehicle_details = vehicle_details
        self.fuel_consumption = fuel_consumption
        self.route_info = route_info
        self.accommodations = accommodations

    def generate_report(self):
        pdf = fpdf.FPDF()
        pdf.add_page()

        pdf.set_font('Arial', 'B', 12)
        pdf.cell(0, 10, 'Trip Planning Report', ln=True, align='C')

        pdf.set_font('Arial', '', 12)
        pdf.ln(10)
        pdf.cell(0, 10, f'Location: {self.location}', ln=True)
        pdf.cell(0, 10, f'Vehicle Details: {self.vehicle_details}', ln=True)
        pdf.cell(0, 10, f'Fuel Consumption: {self.fuel_consumption}', ln=True)
        pdf.cell(0, 10, f'Route Information: {self.route_info}', ln=True)
        pdf.cell(0, 10, f'Accommodations: {self.accommodations}', ln=True)

        filename = f'trip_planning_report_{self.location.replace(" ", "_")}.pdf'
        pdf.output(filename)
        return filename

# Example Usage
if __name__ == '__main__':
    report = TripPlannerReport(
        location='Paris',
        vehicle_details='Toyota Camry 2020',
        fuel_consumption='30 MPG',
        route_info='Straight through the countryside',
        accommodations='Hotel Le Meurice'
    )
    report.generate_report()