"""Config model for storing runtime configuration in database"""

from gatekeeper.models.base import db, TimestampMixin
import json


class Config(db.Model, TimestampMixin):
    """
    Key-value store for runtime configuration.
    Allows changing settings without restarting the service.
    """
    __tablename__ = 'config'

    key = db.Column(db.String(100), primary_key=True)
    _value = db.Column('value', db.Text)
    description = db.Column(db.Text)

    @property
    def value(self):
        """Get value, attempting JSON parse for complex types"""
        if self._value is None:
            return None
        try:
            return json.loads(self._value)
        except json.JSONDecodeError:
            return self._value

    @value.setter
    def value(self, val):
        """Set value, JSON encoding complex types"""
        if isinstance(val, (dict, list)):
            self._value = json.dumps(val)
        elif val is None:
            self._value = None
        else:
            self._value = str(val)

    @classmethod
    def get(cls, key: str, default=None):
        """Get a config value by key"""
        config = cls.query.get(key)
        return config.value if config else default

    @classmethod
    def set(cls, key: str, value, description: str = None):
        """Set a config value"""
        config = cls.query.get(key)
        if config:
            config.value = value
            if description:
                config.description = description
        else:
            config = cls(key=key, description=description)
            config.value = value
            db.session.add(config)
        db.session.commit()
        return config

    def to_dict(self) -> dict:
        """Convert config to dictionary for JSON serialization"""
        return {
            'key': self.key,
            'value': self.value,
            'description': self.description,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }

    def __repr__(self):
        return f'<Config {self.key}>'
