import os

from fastapi import APIRouter, Request, HTTPException
from starlette.responses import RedirectResponse
from authlib.integrations.starlette_client import OAuth
from backend.AuthConfig import GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET
from dotenv import load_dotenv

router = APIRouter()
oauth = OAuth()
load_dotenv()

oauth.register(
    name='google',
    client_id=GOOGLE_CLIENT_ID,
    client_secret=GOOGLE_CLIENT_SECRET,
    server_metadata_url='https://accounts.google.com/.well-known/openid-configuration',
    client_kwargs={
        'scope': 'openid email profile https://www.googleapis.com/auth/calendar'  # Permissão total
    }
)

@router.get("/login/google")
async def login_with_google(request: Request):
    redirect_uri = request.url_for('auth_google_callback')
    return await oauth.google.authorize_redirect(request, redirect_uri)


@router.get("/login/google/callback")
async def auth_google_callback(request: Request):
    try:
        token = await oauth.google.authorize_access_token(request)

        user_info = {
            'access_token': token.get('access_token'),
            'id_token': token.get('id_token'),
            'email': token.get('userinfo', {}).get('email'),
            'name': token.get('userinfo', {}).get('name'),
            'given_name': token.get('userinfo', {}).get('given_name'),
            'family_name': token.get('userinfo', {}).get('family_name'),
            'picture': token.get('userinfo', {}).get('picture'),
            'expires_at': token.get('expires_at')
        }

        if not user_info['email']:
            raise HTTPException(status_code=400, detail="Email não encontrado nos dados do usuário")

        request.session['user'] = user_info

        print("Dados do usuário que serão armazenados:", request.session['user'])

        return {"token": token, "user": user_info}

    except HTTPException:
        raise
    except Exception as e:
        print(f"Erro detalhado durante o callback: {str(e)}")
        return RedirectResponse(url="/auth-error?message=Erro na autenticação")
