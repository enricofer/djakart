function generateDiff(subpath,versione,commit,parent) {
    const baseElement = document.getElementById('version-source-diff')
    if (!baseElement) {
    } else {
        const base = baseElement.options[baseElement.selectedIndex].value
        if (base != 'PARENT') {
            parent = base
        }
    } // /versioni/diff/{versione}/{commit}/{parent}/
    window.open(`${subpath}/djakart/diff/${versione}/${commit}/${parent}/`, '_blank');
}