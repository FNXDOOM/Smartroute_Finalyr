# 🚌 SmartRouteAI — Industrial Shared Mobility Optimization System

> An AI-powered intelligent shared mobility platform designed to optimize urban transportation through dynamic passenger clustering, virtual pickup stops, real road-network routing, vehicle route optimization, and demand prediction.

---

## 📌 Table of Contents

- [Overview](#overview)
- [Core Features](#core-features)
- [System Architecture](#system-architecture)
- [Tech Stack](#tech-stack)
- [Major Algorithms](#major-algorithms)
- [Workflows](#workflows)
- [Database Schema](#database-schema)
- [API Reference](#api-reference)
- [Project Structure](#project-structure)
- [Installation](#installation)
- [MVP Features](#mvp-features)
- [Future Enhancements](#future-enhancements)
- [Objective](#objective)

---

## Overview

SmartRouteAI is a scalable, AI-driven shared mobility optimization platform that improves urban transportation efficiency. It intelligently groups passengers, generates virtual pickup stops, routes vehicles on real road networks, and predicts future demand — all in real time.

---

## Core Features

| Feature | Description |
|---|---|
| 🧠 Intelligent Passenger Matching | Uses H3 spatial indexing + HDBSCAN clustering to group nearby passengers |
| 📍 Dynamic Virtual Stops | Generates optimal pickup/drop-off points based on cluster geometry |
| 🗺️ Real Road-Network Routing | Leverages OpenStreetMap data via OSMnx and NetworkX |
| 🚐 Vehicle Route Optimization | Solves Vehicle Routing Problems (VRP) using Google OR-Tools |
| 🔁 Vehicle Assignment Engine | Hungarian Algorithm for optimal vehicle-to-route matching |
| 📈 Demand Prediction | XGBoost model forecasts ride demand by zone and time |

---

## System Architecture

```
Frontend (React + Leaflet)
        ↓
FastAPI Backend
        ↓
H3 Spatial Partitioning
        ↓
HDBSCAN Passenger Clustering
        ↓
Virtual Stop Generation
        ↓
Road Network Snapping (OSMnx)
        ↓
OR-Tools Route Optimization
        ↓
Vehicle Assignment Engine
        ↓
Demand Prediction Module (XGBoost)
        ↓
PostgreSQL + PostGIS
```

---

## Tech Stack

### Frontend
- **React.js** — Component-based UI
- **Tailwind CSS** — Utility-first styling
- **React Leaflet** — Interactive map rendering

### Backend
- **FastAPI** — High-performance async Python API
- **Python 3.10+**

### Database
- **PostgreSQL** — Relational data storage
- **PostGIS** — Geospatial extensions for PostgreSQL

### AI / Optimization
- **H3** — Hexagonal spatial indexing (Uber)
- **HDBSCAN** — Density-based passenger clustering
- **OR-Tools** — Google's VRP solver
- **XGBoost** — Gradient boosting for demand forecasting
- **NetworkX** — Graph-based road network analysis
- **OSMnx** — OpenStreetMap network data retrieval

---

## Major Algorithms

| Problem | Algorithm |
|---|---|
| Spatial Partitioning | H3 Hexagonal Indexing |
| Passenger Clustering | HDBSCAN |
| Virtual Stop Selection | K-Medoids |
| Shortest Path Routing | A* Algorithm |
| Route Optimization | OR-Tools VRP Solver |
| Vehicle Assignment | Hungarian Algorithm |
| Demand Prediction | XGBoost |

---

## Workflows

### 🔵 Virtual Stop Workflow

```
Ride Requests
      ↓
H3 Spatial Bucketing
      ↓
HDBSCAN Passenger Clustering
      ↓
Generate Candidate Virtual Stops
      ↓
Snap To Nearest Road Node
      ↓
Evaluate Stop Cost
      ↓
Select Best Virtual Stop
```

### 🟢 Route Optimization Workflow

```
Clustered Passengers
      ↓
Generate Pickup/Drop Nodes
      ↓
Construct Vehicle Routing Graph
      ↓
Apply OR-Tools VRP Solver
      ↓
Generate Optimized Shared Route
```

---

## Database Schema

### Users
| Column | Type |
|---|---|
| id | UUID / Integer PK |
| name | VARCHAR |
| email | VARCHAR (unique) |
| password_hash | VARCHAR |

### Vehicles
| Column | Type |
|---|---|
| id | UUID / Integer PK |
| current_location | GEOMETRY(Point) |
| capacity | INTEGER |
| status | VARCHAR (idle/active) |

### Ride Requests
| Column | Type |
|---|---|
| id | UUID / Integer PK |
| user_id | FK → Users |
| pickup_location | GEOMETRY(Point) |
| destination_location | GEOMETRY(Point) |
| request_time | TIMESTAMP |

### Virtual Stops
| Column | Type |
|---|---|
| id | UUID / Integer PK |
| coordinates | GEOMETRY(Point) |
| cluster_id | INTEGER |

---

## API Reference

| Endpoint | Method | Description |
|---|---|---|
| `/auth/register` | POST | Register a new user |
| `/auth/login` | POST | Authenticate and get token |
| `/rides/request` | POST | Submit a new ride request |
| `/rides/status` | GET | Check status of a ride |
| `/cluster/create` | POST | Trigger passenger clustering |
| `/route/optimize` | POST | Run VRP route optimization |
| `/vehicle/assign` | POST | Assign vehicles to routes |
| `/predict/demand` | GET | Forecast demand by zone/time |

---

## Project Structure

```
smartrouteai/
├── README.md
├── requirements.txt
├── .env.example
├── docker-compose.yml
│
├── backend/
│   ├── main.py                    # FastAPI app entrypoint
│   ├── config.py                  # Environment & DB config
│   ├── database.py                # DB connection & session
│   │
│   ├── models/                    # SQLAlchemy ORM models
│   │   ├── user.py
│   │   ├── vehicle.py
│   │   ├── ride_request.py
│   │   └── virtual_stop.py
│   │
│   ├── schemas/                   # Pydantic request/response schemas
│   │   ├── user.py
│   │   ├── vehicle.py
│   │   ├── ride_request.py
│   │   └── virtual_stop.py
│   │
│   ├── routers/                   # API route handlers
│   │   ├── auth.py
│   │   ├── rides.py
│   │   ├── cluster.py
│   │   ├── route.py
│   │   ├── vehicle.py
│   │   └── predict.py
│   │
│   ├── services/                  # Core business logic
│   │   ├── clustering/
│   │   │   ├── h3_partitioner.py      # H3 spatial bucketing
│   │   │   └── hdbscan_clusterer.py   # HDBSCAN passenger grouping
│   │   │
│   │   ├── stops/
│   │   │   ├── virtual_stop_generator.py  # K-Medoids stop generation
│   │   │   └── road_snapper.py            # Snap stops to road nodes
│   │   │
│   │   ├── routing/
│   │   │   ├── graph_builder.py       # OSMnx road graph builder
│   │   │   ├── astar_router.py        # A* shortest path
│   │   │   └── vrp_solver.py          # OR-Tools VRP optimizer
│   │   │
│   │   ├── assignment/
│   │   │   └── hungarian_assigner.py  # Vehicle assignment engine
│   │   │
│   │   └── prediction/
│   │       ├── demand_model.py        # XGBoost demand predictor
│   │       └── feature_engineering.py
│   │
│   └── utils/
│       ├── auth_utils.py          # JWT helpers
│       ├── geo_utils.py           # Geometry helpers
│       └── logger.py
│
├── frontend/
│   ├── package.json
│   ├── tailwind.config.js
│   ├── public/
│   │   └── index.html
│   └── src/
│       ├── App.jsx
│       ├── index.jsx
│       ├── components/
│       │   ├── MapView.jsx            # React Leaflet map
│       │   ├── RideBooking.jsx        # Booking form
│       │   ├── RouteDisplay.jsx       # Optimized route overlay
│       │   └── DemandHeatmap.jsx      # Demand visualization
│       ├── pages/
│       │   ├── Home.jsx
│       │   ├── Login.jsx
│       │   └── Dashboard.jsx
│       ├── services/
│       │   └── api.js                 # Axios API client
│       └── styles/
│           └── index.css
│
├── ml/
│   ├── train_demand_model.py      # XGBoost training script
│   ├── evaluate_model.py
│   └── models/
│       └── demand_model.pkl       # Trained model artifact
│
├── scripts/
│   ├── seed_db.py                 # Database seeding script
│   └── test_clustering.py        # Standalone clustering test
│
└── tests/
    ├── test_clustering.py
    ├── test_routing.py
    ├── test_assignment.py
    └── test_api.py
```

---

## Installation

### Prerequisites
- Python 3.10+
- Node.js 18+
- PostgreSQL 14+ with PostGIS extension
- Docker (optional, for containerized setup)

### Backend Setup

```bash
# Clone the repository
git clone https://github.com/your-username/smartrouteai.git
cd smartrouteai

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install Python dependencies
pip install -r requirements.txt

# Copy and configure environment variables
cp .env.example .env
# Edit .env with your DB credentials and secret keys

# Run database migrations
alembic upgrade head

# Start the backend server
uvicorn backend.main:app --reload
```

### Frontend Setup

```bash
cd frontend
npm install
npm run dev
```

### Python Dependencies

```bash
pip install fastapi uvicorn
pip install h3
pip install hdbscan
pip install osmnx
pip install networkx
pip install ortools
pip install xgboost
pip install scipy
pip install psycopg2
pip install sqlalchemy geoalchemy2
pip install python-jose[cryptography]
pip install passlib[bcrypt]
```

---

## MVP Features

- [x] User ride booking interface
- [x] Real map integration (OpenStreetMap via Leaflet)
- [x] Passenger clustering (H3 + HDBSCAN)
- [x] Virtual stop generation (K-Medoids)
- [x] Route optimization (OR-Tools VRP)
- [x] Vehicle assignment (Hungarian Algorithm)
- [x] Route visualization on map

---

## Future Enhancements

- [ ] Real-time GPS tracking
- [ ] Live traffic data integration
- [ ] Dynamic surge pricing engine
- [ ] Reinforcement learning-based optimization
- [ ] Multi-city deployment support

---

## Objective

To develop a scalable, AI-driven shared mobility optimization platform that improves urban transportation efficiency through intelligent passenger clustering, virtual stop generation, and route optimization — reducing travel time, vehicle idle time, and operational costs across urban transit networks.

---

## License

MIT License — feel free to use, modify, and distribute.
