# FastAPI Senate Backend

## Overview
The FastAPI Senate Backend is a robust and scalable application designed to track and provide insights into stock trades made by members of the United States Senate and House of Representatives. Built with FastAPI, this backend serves as a reliable source for data regarding the financial activities of elected officials, contributing to transparency and public awareness.

## Features
- **Real-time Tracking**: Monitors stock trades by senators and representatives.
- **Data Analysis**: Provides tools for analyzing trends and patterns in trading activities.
- **API Endpoints**: Offers a range of endpoints for accessing and retrieving data.
- **Security**: Ensures data integrity and protection through advanced security protocols.

## Tech Stack
- **Backend**: FastAPI
- **Database**: [Specify database used, e.g., PostgreSQL, MongoDB]
- **Deployment**: Linux Debian VM

## Getting Started

### Prerequisites
- Python 3.8+
- FastAPI
- Uvicorn or any ASGI server

### Installation
1. Clone the repository:

```py
git clone https://github.com/haybarcheezy/fastapi-senate-backend.git
```
2. cd fastapi-senate-backend
```py
cd fastapi-senate-backend
```
3. Install the required dependencies:

```py
pip install -r requirements.txt
```

### Running the Application
Run the application using Uvicorn or any ASGI server:

```py
uvicorn main:app --reload
```

The API will be available at `http://localhost:8000`.

## API Documentation
Once the server is running, you can view the API documentation and interact with the API endpoints by visiting `http://localhost:8000/docs`.

