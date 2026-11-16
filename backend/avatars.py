import base64
import io
import warnings
from fastapi import Depends, HTTPException
from pydantic import Field
from PIL import Image, ImageOps
from .schemas import Input

class AvatarInput(Input):
    image: str = Field(max_length=45000)


def normalize(value):
    if not value:
        return ''
    try:
        prefix,encoded=value.split(',',1)
        if prefix not in ('data:image/jpeg;base64','data:image/png;base64'):
            raise ValueError()
        content=base64.b64decode(encoded,validate=True)
        with warnings.catch_warnings():
            warnings.simplefilter('error',Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(content),formats=['JPEG','PNG']) as image:
                if image.width>512 or image.height>512:
                    raise ValueError()
                image.load()
                thumbnail=ImageOps.fit(ImageOps.exif_transpose(image).convert('RGB'),(96,96))
                output=io.BytesIO()
                thumbnail.save(output,format='JPEG',quality=80)
        return 'data:image/jpeg;base64,'+base64.b64encode(output.getvalue()).decode()
    except Exception:
        raise HTTPException(422,detail={'code':'INVALID_AVATAR','message':'Выберите корректное фото JPEG или PNG.'}) from None


def install(app,current_user,db,user_json,audit):
    @app.put('/api/auth/avatar',tags=['Auth'])
    def avatar(data:AvatarInput,user=Depends(current_user),session=Depends(db)):
        user.avatar=normalize(data.image)
        audit(session,user,'profile.avatar')
        session.commit()
        return user_json(user)
