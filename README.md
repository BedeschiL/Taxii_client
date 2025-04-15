# TAXII Feed Viewer Client

This is a Flask-based web application to view and manage TAXII 2.1 feeds, designed to work with the accompanying simple TAXII server.

## Setup

1.  **Prerequisites:**
    *   Python 3.7+
    *   pip

2.  **Installation:**
    ```bash
    git clone <repository-url>
    cd <repository-directory>/client # Assuming client code is in a 'client' subdir
    python -m venv venv
    source venv/bin/activate  # On Windows use `venv\Scripts\activate`
    pip install -r requirements.txt
    ```

3.  **Running the Client:**
    ```bash
    flask run --host=0.0.0.0 --port=5000
    # Or directly: python app.py
    ```
    The application will be available at `http://localhost:5000`.

4.  **Running the Server:**
    *   Follow the instructions in the server's `README.md` to build and run the TAXII server using Docker Compose. It typically runs on port 6100.
    *   Ensure the server's database is initialized (`init_database.py`).

## Usage

1.  Open `http://localhost:5000` in your browser.
2.  Use the "Discover Server Info" section first:
    *   Enter the server's **base URL** (e.g., `http://localhost:6100`).
    *   Enter the server's credentials (`api_user` / `api_password` by default).
    *   Click "Discover API Roots". Copy the desired API Root URL (e.g., `http://localhost:6100/example1/`).
    *   Paste the API Root URL into the "Discover Collections" section.
    *   Click "Discover Collections". Copy the **Title** of the collection you want to add (e.g., `High Value Indicator Collection`).
3.  Use the "Feed Management" section:
    *   Enter a name for your feed.
    *   Paste the **API Root URL** you copied.
    *   Paste the **Collection Title** you copied.
    *   Enter the username and password (`api_user` / `api_password`).
    *   Click "Add Feed".
4.  Click "Refresh All" to fetch indicators from the configured feeds.
5.  Use the search bar to filter indicators.
6.  Click the eye icon (<i class="fas fa-eye"></i>) next to an indicator to view its details and raw STIX data.

## Data Storage

*   Feed configurations are stored in `taxii_feeds.json`.
*   Fetched indicators are stored in `indicators.json`. Delete this file to clear cached indicators.