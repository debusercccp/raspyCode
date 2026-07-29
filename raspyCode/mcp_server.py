import sys
from pathlib import Path

from mcp.server.fastmcp import FastMCP

# Assicura che il pacchetto raspyCode sia risolvibile
sys.path.append(str(Path(__file__).resolve().parent.parent))
from raspyCode.bioCli.sequence import dnaToRna, gcContent, revComp

# Inizializza il server MCP per la bioinformatica
mcp = FastMCP("RaspyCode-BioToolkit")

@mcp.tool()
def calculate_gc_content(sequence: str) -> str:
    """Calcola la percentuale del contenuto GC in una sequenza DNA/RNA."""
    try:
        res = gcContent.gc_content(sequence)
        return f"GC Content: {res}%"
    except Exception as e:
        return f"Errore nel calcolo del GC Content: {str(e)}"

@mcp.tool()
def reverse_complement(sequence: str) -> str:
    """Restituisce il filamento complementare inverso di una sequenza DNA."""
    try:
        return revComp.rev_comp(sequence)
    except Exception as e:
        return f"Errore nel calcolo del Reverse Complement: {str(e)}"

@mcp.tool()
def translate_dna_to_rna(sequence: str) -> str:
    """Trascrive una sequenza di DNA nel corrispondente filamento di RNA."""
    try:
        return dnaToRna.dna_to_rna(sequence)
    except Exception as e:
        return f"Errore nella trascrizione DNA->RNA: {str(e)}"

if __name__ == "__main__":
    # Avvia il server in modalità standard input/output (JSON-RPC)
    mcp.run(transport='stdio')
