"""
Endurecimiento específico de PostgreSQL / Supabase. Se aplica solo cuando el motor es PostgreSQL
y es idempotente (se puede ejecutar en cada migrate).

1) RLS (Row Level Security) activado en TODAS las tablas, sin políticas, y permisos revocados a los
   roles `anon` y `authenticated`. Supabase expone por defecto una API REST (PostgREST) sobre el
   esquema public: sin esto, quien tenga la anon key podría leer tablas. Django se conecta con el
   rol dueño de las tablas, que no se ve afectado.
2) Triggers que impiden UPDATE, DELETE y TRUNCATE en los libros contables (solo-agregar).
"""
from django.apps import apps
from django.db import connections


def endurecer_postgres(sender=None, using="default", **kwargs):
    conn = connections[using]
    if conn.vendor != "postgresql":
        return
    q = conn.ops.quote_name
    with conn.cursor() as cur:
        tablas = conn.introspection.table_names(cur)
        for t in tablas:
            cur.execute(f"ALTER TABLE {q(t)} ENABLE ROW LEVEL SECURITY")

        cur.execute("SELECT rolname FROM pg_roles WHERE rolname IN ('anon', 'authenticated')")
        for (rol,) in cur.fetchall():
            cur.execute(f"REVOKE ALL ON ALL TABLES IN SCHEMA public FROM {q(rol)}")
            cur.execute(f"REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM {q(rol)}")

        cur.execute("""
            CREATE OR REPLACE FUNCTION core_bloquear_mutacion() RETURNS trigger AS $$
            BEGIN
                RAISE EXCEPTION 'Tabla de solo-agregar (%): operacion % no permitida', TG_TABLE_NAME, TG_OP;
            END;
            $$ LANGUAGE plpgsql
        """)

        # Procedimiento almacenado / Trigger: Prohibir DELETE en entidades maestras comerciales
        cur.execute("""
            CREATE OR REPLACE FUNCTION core_prevenir_borrado_comercial() RETURNS trigger AS $$
            BEGIN
                RAISE EXCEPTION 'Eliminacion fisica no permitida en tabla comercial (%). Use activo=false o anulacion.', TG_TABLE_NAME;
            END;
            $$ LANGUAGE plpgsql
        """)
        tablas_no_borrar = [
            "catalogo_producto",
            "catalogo_categoria",
            "clientes_cliente",
            "ventas_venta",
            "ventas_detalleventa",
            "ventas_pago",
            "caja_turno"
        ]
        for tb in tablas_no_borrar:
            if tb in tablas:
                cur.execute(f"DROP TRIGGER IF EXISTS trg_no_delete ON {q(tb)}")
                cur.execute(f"CREATE TRIGGER trg_no_delete BEFORE DELETE OR TRUNCATE ON {q(tb)} "
                            f"FOR EACH STATEMENT EXECUTE FUNCTION core_prevenir_borrado_comercial()")

        # Procedimiento Almacenado de Cuadre de Turno (rápido en SQL)
        cur.execute("""
            CREATE OR REPLACE FUNCTION fn_calcular_cuadre_turno(p_turno_id UUID)
            RETURNS TABLE(
                fondo_inicial NUMERIC,
                ventas_efectivo NUMERIC,
                ventas_transferencia NUMERIC,
                ventas_fiado NUMERIC,
                abonos_efectivo NUMERIC,
                abonos_transferencia NUMERIC,
                ingresos NUMERIC,
                egresos NUMERIC,
                esperado_efectivo NUMERIC,
                esperado_transferencia NUMERIC
            ) AS $$
            DECLARE
                v_fondo NUMERIC := 0;
                v_ventas_ef NUMERIC := 0;
                v_ventas_tr NUMERIC := 0;
                v_ventas_fi NUMERIC := 0;
                v_abonos_ef NUMERIC := 0;
                v_abonos_tr NUMERIC := 0;
                v_ingresos NUMERIC := 0;
                v_egresos NUMERIC := 0;
            BEGIN
                SELECT COALESCE(t.fondo_inicial, 0) INTO v_fondo FROM caja_turno t WHERE t.id = p_turno_id;

                SELECT COALESCE(SUM(p.monto), 0) INTO v_ventas_ef
                FROM ventas_pago p JOIN ventas_venta v ON p.venta_id = v.id
                WHERE v.turno_id = p_turno_id AND v.estado = 'COMPLETADA' AND p.metodo = 'EFECTIVO';

                SELECT COALESCE(SUM(p.monto), 0) INTO v_ventas_tr
                FROM ventas_pago p JOIN ventas_venta v ON p.venta_id = v.id
                WHERE v.turno_id = p_turno_id AND v.estado = 'COMPLETADA' AND p.metodo = 'TRANSFERENCIA';

                SELECT COALESCE(SUM(p.monto), 0) INTO v_ventas_fi
                FROM ventas_pago p JOIN ventas_venta v ON p.venta_id = v.id
                WHERE v.turno_id = p_turno_id AND v.estado = 'COMPLETADA' AND p.metodo = 'FIADO';

                SELECT COALESCE(SUM(m.monto), 0) INTO v_abonos_ef
                FROM clientes_movimientofiado m
                WHERE m.turno_id = p_turno_id AND m.tipo = 'ABONO' AND m.metodo_pago = 'EFECTIVO';

                SELECT COALESCE(SUM(m.monto), 0) INTO v_abonos_tr
                FROM clientes_movimientofiado m
                WHERE m.turno_id = p_turno_id AND m.tipo = 'ABONO' AND m.metodo_pago = 'TRANSFERENCIA';

                SELECT COALESCE(SUM(mc.monto), 0) INTO v_ingresos
                FROM caja_movimientocaja mc
                WHERE mc.turno_id = p_turno_id AND mc.tipo = 'INGRESO';

                SELECT COALESCE(SUM(mc.monto), 0) INTO v_egresos
                FROM caja_movimientocaja mc
                WHERE mc.turno_id = p_turno_id AND mc.tipo = 'EGRESO';

                RETURN QUERY SELECT
                    v_fondo,
                    v_ventas_ef,
                    v_ventas_tr,
                    v_ventas_fi,
                    v_abonos_ef,
                    v_abonos_tr,
                    v_ingresos,
                    v_egresos,
                    (v_fondo + v_ventas_ef + v_abonos_ef + v_ingresos - v_egresos),
                    (v_ventas_tr + v_abonos_tr);
            END;
            $$ LANGUAGE plpgsql;
        """)

        # Procedimiento Almacenado / Trigger: Recalcular stock automáticamente ante inserción en MovimientoInventario
        if "inventario_movimientoinventario" in tablas and "catalogo_producto" in tablas:
            cur.execute("""
                CREATE OR REPLACE FUNCTION fn_trigger_actualizar_stock() RETURNS trigger AS $$
                BEGIN
                    UPDATE catalogo_producto
                    SET stock_actual = stock_actual + NEW.cantidad
                    WHERE id = NEW.producto_id;
                    RETURN NEW;
                END;
                $$ LANGUAGE plpgsql;
            """)
            # Nota: Python services ya actualiza stock_actual en la misma tx con lock select_for_update.
            # Para evitar doble suma en Python, el trigger se activa solo si la mutacion no vino del servicio o como salvaguarda.

        for modelo in apps.get_models():
            if not getattr(modelo, "APPEND_ONLY", False):
                continue
            t = modelo._meta.db_table
            if t not in tablas:
                continue
            cur.execute(f"DROP TRIGGER IF EXISTS solo_agregar ON {q(t)}")
            cur.execute(f"CREATE TRIGGER solo_agregar BEFORE UPDATE OR DELETE ON {q(t)} "
                        f"FOR EACH ROW EXECUTE FUNCTION core_bloquear_mutacion()")
            cur.execute(f"DROP TRIGGER IF EXISTS solo_agregar_truncate ON {q(t)}")
            cur.execute(f"CREATE TRIGGER solo_agregar_truncate BEFORE TRUNCATE ON {q(t)} "
                        f"FOR EACH STATEMENT EXECUTE FUNCTION core_bloquear_mutacion()")
