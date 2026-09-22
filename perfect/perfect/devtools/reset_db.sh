rm -rf migrations/ *.db* && \
python -m flask --app perfect.app db init && \
python -m flask --app perfect.app db migrate -m "Initial migration." && \
python -m flask --app perfect.app db upgrade && \
python -m flask --app perfect.app components load_components
