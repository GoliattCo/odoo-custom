# Club - Servicios

#club

[[🗺️ Mapa del Proyecto]] > [[Club Core]]

---

## Módulos de Servicios

### club_events
**Depends:** `club_core`, `event`, `website_event`, `payment`  
Eventos del club integrados con el portal web y pagos online.

### club_guests
**Depends:** `club_core`, `mail`  
Registro y gestión de invitados de socios.

### club_affiliate_billing
**Depends:** `club_core`, `club_pos`, `account`, `mail`  
Facturación periódica a afiliados, cargos de membresía.

### club_affiliate_employees
**Depends:** `club_core`  
Empleados que también son afiliados al club.

### club_access_control
**Depends:** `club_core`, `club_guests`, `club_affiliate_employees`, `club_events`, `club_tournaments`  
Control de acceso físico al club — valida socios, invitados y asistentes a eventos.

### club_pos
**Depends:** `point_of_sale`, `club_core`  
Punto de venta integrado con la membresía del club.

### club_tournaments
**Depends:** `club_core`, `mail`  
Gestión de torneos y competencias.

### club_news
**Depends:** `club_core`, `mail`  
Publicación de noticias y anuncios para socios.

### club_pqr
**Depends:** `club_core`, `mail`  
Sistema de Peticiones, Quejas y Reclamos.

### club_assembly
**Depends:** `club_core`, `mail`  
Gestión de asambleas de socios, votaciones, actas.

### club_faq
**Depends:** `club_core`  
Base de preguntas frecuentes para socios.

### club_job_offers
**Depends:** `club_core`, `mail`  
Ofertas de empleo internas del club.

### club_lost_found
**Depends:** `club_core`, `mail`  
Registro de objetos perdidos y encontrados.

### club_object_loan
**Depends:** `club_core`  
Préstamo de objetos/equipos del club a socios.
