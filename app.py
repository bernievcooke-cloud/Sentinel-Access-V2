# Define the refresh button handler

def refresh_button_clicked():
    # Clear all session state variables
    if 'selected_reports' in session:
        del session['selected_reports']
    if 'username' in session:
        del session['username']
    if 'user_email' in session:
        del session['user_email']
    if 'geocode_result' in session:
        del session['geocode_result']
    if 'geocode_search_term' in session:
        del session['geocode_search_term']
    if 'progress_status' in session:
        del session['progress_status']
    
    # Optionally, redirect or render the app as needed
