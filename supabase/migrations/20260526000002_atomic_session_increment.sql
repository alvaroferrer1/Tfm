-- Función atómica para incrementar contadores de sesión sin race condition.
-- Sustituye el patrón SELECT→UPDATE que tenía race condition bajo concurrencia.

CREATE OR REPLACE FUNCTION increment_session_stats(
    p_session_id TEXT,
    p_tools      INT DEFAULT 0,
    p_kuine      INT DEFAULT 0
)
RETURNS VOID
LANGUAGE SQL
AS $$
    UPDATE agent_sessions
    SET
        messages_count = messages_count + 1,
        tools_called   = tools_called   + p_tools,
        kuine_calls    = kuine_calls    + p_kuine
    WHERE id = p_session_id;
$$;
