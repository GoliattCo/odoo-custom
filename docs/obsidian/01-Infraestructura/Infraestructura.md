# Infraestructura

#infraestructura

[[🗺️ Mapa del Proyecto]]

---

## Docker

| Contenedor | Rol |
|------------|-----|
| `odoo-odoo-1` | Servidor Odoo 19 |
| `odoo-db-1` | PostgreSQL |

**Acceso web:** http://localhost:8069  
**Login:** admin / admin  
**Idioma:** es_CO (Español - Colombia)

---

## Base de Datos

| Campo | Valor |
|-------|-------|
| Nombre | `odoo-club19` |
| Usuario | `odoo` |
| Contraseña | `odoo` |

```bash
# Conectar a la BD
docker exec odoo-db-1 psql -U odoo -d odoo-club19
```

---

## Rutas de Archivos

| Propósito | Host | Contenedor |
|-----------|------|------------|
| Odoo fuente | `/Users/manuelcaro/Odoo/odoo` | `/odoo` |
| Custom addons | `/Users/manuelcaro/Odoo/custom-addons` | `/mnt/custom-addons` |
| Jorels addons | `/Users/manuelcaro/Odoo/addons/jorels-odoo-addons` | `/mnt/jorels-addons` |
| Config | `/Users/manuelcaro/Odoo/config/odoo.conf` | `/etc/odoo/odoo.conf` |

---

## Comandos Frecuentes

```bash
# Actualizar un módulo
docker exec odoo-odoo-1 /odoo/odoo-bin \
  -c /etc/odoo/odoo.conf \
  -d odoo-club19 \
  -u <nombre_modulo> \
  --stop-after-init

# Reiniciar Odoo
docker restart odoo-odoo-1

# Ver logs en vivo
docker logs -f odoo-odoo-1

# Actualizar módulo + reiniciar (combo usual)
docker exec odoo-odoo-1 /odoo/odoo-bin \
  -c /etc/odoo/odoo.conf \
  -d odoo-club19 \
  -u <modulo> --stop-after-init \
  && docker restart odoo-odoo-1
```

---

## Archivos de Configuración

- `docker-compose.yml` — definición de servicios
- `Dockerfile` — imagen Odoo personalizada
- `Dockerfile.railway` — imagen para Railway
- `railway.toml` — config Railway deployment
- `railway-entrypoint.sh` — script de arranque Railway
- `config/odoo.conf` — parámetros Odoo

---

## Addons de Terceros

- **Jorels:** `/Users/manuelcaro/Odoo/addons/jorels-odoo-addons`  
  Incluye módulos para Colombia (e.g. `l10n_co_*`)
