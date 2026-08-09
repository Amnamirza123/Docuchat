"""
Central Supabase client.

Two clients on purpose:
- `supabase_admin` uses the SERVICE ROLE key and bypasses RLS. The backend
  uses this for writes it does on behalf of an already-verified user
  (e.g. inserting chunks after upload).
- `get_user_client(access_token)` uses the ANON key + the user's own JWT,
  so any query made with it is automatically RLS-scoped to that user.
  Use this whenever you're just reading/writing data a user should only
  ever see their own copy of, as a second layer of safety on top of RLS.
"""

from supabase import create_client, Client
from config import settings

# Admin client — full access, backend-only, never exposed to the frontend
supabase_admin: Client = create_client(
    settings.supabase_url,
    settings.supabase_service_role_key,
)


def get_user_client(access_token: str) -> Client:
    """Returns a Supabase client scoped to the requesting user's own JWT."""
    client = create_client(settings.supabase_url, settings.supabase_anon_key)
    client.postgrest.auth(access_token)
    return client


def verify_user(access_token: str) -> dict:
    """
    Verifies a Supabase JWT and returns the user record.
    Raises if the token is invalid/expired — callers should catch this
    and return a 401.
    """
    response = supabase_admin.auth.get_user(access_token)
    if response is None or response.user is None:
        raise ValueError("Invalid or expired token")
    return response.user