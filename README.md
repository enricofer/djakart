# Djakart

A django app for [kart versioning](https://kartproject.org/)

## Deployment

1. clone the repository and enter djakart folder

```
$ git clone git@github.com:enricofer/djakart.git
$ cd djakart
```

2. **remove** pgdata git placeholder. initdb.sh check id pgdata directory  and stops the db initialization if the folder is not empty.

```
$ rm ./data/pgdata/readme.txt
```

3. start the container

```
$ docker compose up -d
```

4. collect necessary static files

```
$ docker compose exec webapp_djakart /usr/bin/python3 manage.py collectstatic --no-input
```

5. create the superuser

```
$ docker compose exec webapp_djakart /usr/bin/python3 manage.py createsuperuser --no-input
```

6. login to [http://localhost:9889/admin](http://localhost:9889/admin)

```
login: djakart
password: letmein
```

![](/doc/screenshot01.png)
