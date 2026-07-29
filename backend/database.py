import ssl
from urllib.parse import urlparse, urlunparse, parse_qsl, urlencode
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from backend.config import settings

db_url = settings.DATABASE_URL

# Auto-resolve dialect to postgresql+pg8000 if standard prefix is used
if db_url.startswith("postgresql://"):
    db_url = "postgresql+pg8000://" + db_url[len("postgresql://"):]

# Parse the URL to extract query parameters and hostname
parsed_url = urlparse(db_url)
queries = dict(parse_qsl(parsed_url.query))

# Enable SSL if explicit parameters are present or if it's a Neon cloud host
has_ssl = "sslmode" in queries or "ssl" in queries or (parsed_url.hostname and "neon.tech" in parsed_url.hostname)

# Strip pg8000-incompatible parameters from URL query string
queries.pop("sslmode", None)
queries.pop("ssl", None)

# Reassemble the clean URL
new_query = urlencode(list(queries.items()))
clean_url = urlunparse((
    parsed_url.scheme,
    parsed_url.netloc,
    parsed_url.path,
    parsed_url.params,
    new_query,
    parsed_url.fragment
))

# Setup connection arguments for pg8000
connect_args = {}
if has_ssl:
    ssl_context = ssl.create_default_context()
    connect_args["ssl_context"] = ssl_context

# Create SQLAlchemy connection engine
engine = create_engine(
    clean_url,
    pool_pre_ping=True,
    connect_args=connect_args
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
