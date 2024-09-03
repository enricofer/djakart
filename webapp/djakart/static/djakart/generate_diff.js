function generateDiff(subpath,versione,commit,parent) {
    const baseElement = document.getElementById('version-source-diff')
    const base = baseElement.options[baseElement.selectedIndex].value
    if (base != 'PARENT') {
        parent = commit
        commit = base
    } // /versioni/diff/{versione}/{commit}/{parent}/
    window.open(`${subpath}/djakart/diff/${versione}/${commit}/${parent}/`, '_blank');
}