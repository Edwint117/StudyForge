"""Contain parsing/sampling as well as symbolic work inside the RPC's time budget."""

from multiprocessing import get_context
from multiprocessing.connection import Connection


def _run(pipe: Connection, answer: str, expected: str) -> None:
    try:
        from engine.algorithms.verification import check_sympy

        result = check_sympy(answer, expected)
        pipe.send({"verdict": result.verdict.value, "method": result.method})
    except Exception:
        pipe.send({"verdict": "undetermined", "method": "sympy"})
    finally:
        pipe.close()


def bounded_check(answer: str, expected: str, timeout: float = 1.8) -> dict[str, str]:
    context = get_context("spawn")
    reader, writer = context.Pipe(duplex=False)
    # Daemonic children cannot spawn grandchildren. If the reference asks for its
    # symbolic pool, return undetermined; the online review path supports self-grade.
    process = context.Process(target=_run, args=(writer, answer, expected), daemon=True)
    try:
        process.start()
        writer.close()
        if reader.poll(timeout):
            result = reader.recv()
            if isinstance(result, dict) and result.get("verdict") in ("correct", "incorrect", "undetermined"):
                return {"verdict": str(result["verdict"]), "method": str(result["method"])}
        return {"verdict": "undetermined", "method": "sympy"}
    except (EOFError, OSError):
        return {"verdict": "undetermined", "method": "sympy"}
    finally:
        if process.is_alive():
            process.kill()
        if process.pid is not None:
            process.join(timeout=0.2)
            process.close()
        reader.close()
        writer.close()
