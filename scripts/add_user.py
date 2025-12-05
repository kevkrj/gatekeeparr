#!/usr/bin/env python3
"""
Add User Script for Gatekeeper

Usage (from host):
    docker exec gatekeeper python /app/scripts/add_user.py <username> <user_type> [max_rating]

Examples:
    docker exec gatekeeper python /app/scripts/add_user.py kevin admin
    docker exec gatekeeper python /app/scripts/add_user.py Aubrey kid PG
    docker exec gatekeeper python /app/scripts/add_user.py boyz kid PG-13
    docker exec gatekeeper python /app/scripts/add_user.py mom adult

User Types:
    - admin: Full access, all content auto-approved
    - adult: All content auto-approved (unless requires_approval flag set)
    - teen: Auto-approve up to PG-13, hold R+
    - kid: Auto-approve up to max_rating, hold higher

Max Rating (for kids/teens):
    - G, PG, PG-13, R (default based on user_type)
"""

import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, '/app')

from gatekeeper.app import create_app
from gatekeeper.models import db, User


def add_user(username: str, user_type: str, max_rating: str = None):
    """Add or update a user in the database."""
    app = create_app()

    with app.app_context():
        # Validate user type
        valid_types = ['admin', 'adult', 'teen', 'kid']
        if user_type not in valid_types:
            print(f"Error: Invalid user type '{user_type}'")
            print(f"Valid types: {', '.join(valid_types)}")
            sys.exit(1)

        # Set default max_rating based on user type
        if max_rating is None:
            if user_type == 'kid':
                max_rating = 'PG'
            elif user_type == 'teen':
                max_rating = 'PG-13'

        # Check if user exists
        user = User.query.filter_by(username=username).first()

        if user:
            print(f"Updating existing user: {username}")
            user.user_type = user_type
            user.max_rating = max_rating
        else:
            print(f"Creating new user: {username}")
            user = User(
                username=username,
                user_type=user_type,
                max_rating=max_rating,
            )
            db.session.add(user)

        db.session.commit()

        print(f"\nUser configured:")
        print(f"  Username: {user.username}")
        print(f"  Type: {user.user_type}")
        print(f"  Max Rating: {user.max_rating or 'unlimited'}")
        print(f"\nAll users:")
        for u in User.query.all():
            print(f"  - {u.username}: {u.user_type} (max: {u.max_rating or 'unlimited'})")


def list_users():
    """List all users in the database."""
    app = create_app()

    with app.app_context():
        users = User.query.all()
        if not users:
            print("No users configured yet.")
            print("\nAdd users with:")
            print("  docker exec gatekeeper python /app/scripts/add_user.py <username> <type>")
        else:
            print("Configured users:")
            for u in users:
                print(f"  - {u.username}: {u.user_type} (max: {u.max_rating or 'unlimited'})")


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print(__doc__)
        print("\nCurrent users:")
        list_users()
        sys.exit(0)

    if sys.argv[1] in ['--list', '-l', 'list']:
        list_users()
        sys.exit(0)

    if len(sys.argv) < 3:
        print("Error: Missing arguments")
        print("Usage: add_user.py <username> <user_type> [max_rating]")
        sys.exit(1)

    username = sys.argv[1]
    user_type = sys.argv[2]
    max_rating = sys.argv[3] if len(sys.argv) > 3 else None

    add_user(username, user_type, max_rating)
