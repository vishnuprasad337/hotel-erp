FROM python:3.13-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install  -r requirements.txt

COPY . .

ENV DJANGO_SETTINGS_MODULE=erp.settings
ENV SECRET_KEY=+k+bv9c*$rj26!16)cetgbc+0@8ofqk4$$cj_06ljy6aa_1vn)
ENV DEBUG=False

EXPOSE 8000

CMD python manage.py collectstatic --noinput && \
    python manage.py migrate_schemas --shared && \
    gunicorn erp.wsgi:application --bind 0.0.0.0:$PORT --workers 2 --timeout 120