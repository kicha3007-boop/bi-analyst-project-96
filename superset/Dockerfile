FROM apache/superset:4.1.2

USER root
RUN pip install --no-cache-dir psycopg2-binary==2.9.10
COPY superset_config.py /app/pythonpath/superset_config.py
COPY bootstrap.sh import_dashboard.sh /app/
RUN chmod +x /app/bootstrap.sh /app/import_dashboard.sh
USER superset

CMD ["/app/bootstrap.sh"]
