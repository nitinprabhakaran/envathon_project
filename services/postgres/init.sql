-- Create webhook database
CREATE DATABASE webhook_db;

-- Create streamlit database  
CREATE DATABASE streamlit_db;

-- Switch to webhook_db
\c webhook_db;

-- Create tables for webhook handler
CREATE TABLE webhook_events (
    id SERIAL PRIMARY KEY,
    event_type VARCHAR(50) NOT NULL,
    project_id INTEGER,
    project_name VARCHAR(255),
    payload JSONB,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_webhook_events_type ON webhook_events(event_type);
CREATE INDEX idx_webhook_events_project ON webhook_events(project_id);

-- Switch to streamlit_db
\c streamlit_db;

-- Create tables for streamlit session management
CREATE TABLE sessions (
    id UUID PRIMARY KEY,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_active TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    data JSONB
);

CREATE TABLE chat_messages (
    id SERIAL PRIMARY KEY,
    session_id UUID REFERENCES sessions(id),
    role VARCHAR(20) NOT NULL,
    content TEXT,
    metadata JSONB,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_sessions_active ON sessions(last_active);
CREATE INDEX idx_messages_session ON chat_messages(session_id);