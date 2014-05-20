if exists("loaded_jcall")
  finish
endif
"let loaded_jcall = 1

let g:jcall_path = expand('<sfile>')
let g:jcall_py_path = fnamemodify(g:jcall_path, ":p:h:h").'/py'
let g:jcall_tmp_path = "/tmp/jcall"

function! s:InitDefault(variable, default_value)
    if exists(a:variable) == 0
        execute "let ".a:variable." = ".a:default_value
    endif
endfunction

" Set global defaults
call s:InitDefault('g:jcall_jump', 1)
call s:InitDefault('g:jcall_open', 1)

call s:InitDefault('g:jcall_status', 0)
call s:InitDefault('g:jcall_debug', 0)

function! s:Status(msg)
    if g:jcall_debug || g:jcall_status
        echo a:msg
    endif
endfunction

function! s:Debug(msg)
    if g:jcall_debug
        echom a:msg
    endif
endfunction

function! s:Refresh(build_dir)
    call s:Status("Refreshing java cache")

    let ebp = substitute(a:build_dir, '/', '\\/', 'g')
    let cmd = "find ".a:build_dir." -type f | sed -ne 's/".ebp."\\/\\(.*\\).class/\\1/p'"
    call s:Debug(cmd)
    let classfiles = split(system(cmd), '\n')

    let lines = []
    let all = []
    let packages = {}
    for classfile in classfiles
        let escaped_classfile = substitute(classfile, '\$', '$$', 'g')
        let all += [escaped_classfile.".javap"]
        if match(classfile, '/') != -1
            let package = substitute(classfile, '\(.*\)/.*$', '\1', '')
            let packages[package] = 1
        endif
    endfor

    let default = ["default: \\"]
    call map(all, '"\t\t".v:val." \\"')
    let default += l:all
    let default += [''] "need extra line because last dep has \
    let default += ["\t@if [ \"$(CHANGED)\" == \"1\" ]; then \\"]
    let default += ["\t  rm -f ".g:jcall_tmp_path.a:build_dir.'/classsig.*; \']
    let default += ["\t  rm -f ".g:jcall_tmp_path.a:build_dir.'/linenos.*; \']
    let default += ["\t  /usr/bin/python ".g:jcall_py_path."/extract.py '".a:build_dir."'; \\"]
    let default += ["\tfi"]
    let default += [""]

    "let pattern_rule  = ['%.javap:']
    "let pattern_rule += ['	dir=`dirname ''$@''`; mkdir -p "$$dir"']
    "let pattern_rule += ['	javap -classpath '''.a:build_dir.''' -c -l -private ''$*'' > ''$@''']

    let pattern_rule  = []
    "Default package
    let pattern_rule += ['%.javap:: '.a:build_dir.'/%.class']
    let pattern_rule += ['	$(eval CHANGED=1)']
    let pattern_rule += ['	dir=`dirname ''$@''`; mkdir -p "$$dir"']
    let pattern_rule += ['	javap -classpath '''.a:build_dir.''' -c -l -private ''$*'' > ''$@''']
    let pattern_rule += ['']

    for pkg in keys(packages)
        let pattern_rule += [pkg.'/%.javap:: '.a:build_dir.'/'.pkg.'/%.class']
        let pattern_rule += ['	$(eval CHANGED=1)']
        let pattern_rule += ['	dir=`dirname ''$@''`; mkdir -p "$$dir"']
        let pattern_rule += ['	javap -classpath '''.a:build_dir.''' -c -l -private '''.pkg.'/$*'' > ''$@''']
        let pattern_rule += ['']
    endfor

    let lines = default + [''] + pattern_rule

    call system('mkdir -p '.g:jcall_tmp_path.a:build_dir)
    call writefile(lines, g:jcall_tmp_path.a:build_dir.'/Makefile')
    let data = split(system("/usr/bin/make -rj8 -C ".g:jcall_tmp_path.a:build_dir), '\n')
    if v:shell_error != 0
        echoerr join(data, "\n")
    endif
endfunction

function! s:GetLine(filepath, lineno)
    let lines = readfile(a:filepath)
    return lines[a:lineno-1]
endfunction

function! s:GetMethodSignature(filepath, lineno, build_dir)
    let filename = fnamemodify(a:filepath, ":t")
    call s:Status("Finding Method signature at ".filename.":".a:lineno)
    let javam = '/usr/bin/python '.g:jcall_py_path.'/method.py "'.a:filepath.'" '.a:lineno.' "'.a:build_dir.'"'
    call s:Debug(javam)
    let data = system(javam)
    if v:shell_error != 0
        echoerr "Could not find method signature for ".filename.":".a:lineno.'\n'.data
    else
        let method_signatures = split(data, '\n')
        if len(method_signatures) == 1
            return method_signatures[0]
        else
            let i=0
            while i < len(method_signatures)
                let number = i + 1
                echo number.') '.method_signatures[i]
                let i += 1
            endwhile
            let number = input("Which method?")
            return method_signatures[l:number-1]
        endif
    endif
endfunction

function! s:SelectBestMatch(package, pathlist)
    if len(a:pathlist) == 1
        return a:pathlist[0]
    endif

    call s:Debug("Finding best match with package ".a:package.".")
    let matches = []
    for path in a:pathlist
        if match(path, a:package) >= 0
            let matches += [path]
        endif
    endfor
    if len(matches) > 0
        if len(matches) == 1
            return matches[0]
        else
            "match with shortest path will match the package better
            let shortest_match = ''
            let shortest_match_len = 9999999
            for cur_match in matches
                if len(cur_match) < shortest_match_len
                    let shortest_match = cur_match
                    let shortest_match_len = len(cur_match)
                endif
            endfor
            return shortest_match
        endif
    endif

    "no match with full path, current directory might be set in package direcotry
    let foldernames = a:package
    if len(foldernames) == 0
        echoerr "Could not find match"
    endif

    call remove(foldernames, 0)
    return s:SelectBestMatch(join(foldernames, "/"), pathlist)
endfunction

function! s:GetPath(package, filename, src_dir)
    let location = "."
    if a:src_dir != ''
        let location = a:src_dir
    endif
    let paths = split(system("/usr/bin/find ".location." -type f -name '".a:filename."'"),'\n')
    if len(paths) > 0
        return s:SelectBestMatch(a:package, paths)
    else
        echoerr "Error: could not find file: ".a:filename
    endif
endfunction

function! s:GetCalls(method_signature, src_dir, build_dir)
    call s:Debug("Looking for ".a:method_signature)
    call s:Status("Searching for calls")

    " Signature HAS to be in single quotes otherwise innerclasses (with $)
    " will be mangled
    let search_cmd = '/usr/bin/python '.g:jcall_py_path.'/jcall.py "'.a:build_dir.'" '''.a:method_signature.''''
    call s:Debug("Search: ".search_cmd)
    let invocations = split(system(search_cmd), '\n')
    let quickfix_locations = []
    for invocation in invocations
        let line = split(invocation, ":", 1) " keepempty to support default package
        if len(line) == 3
            let [package, l:file, lineno] = line
            let invpath = s:GetPath(package, file, a:src_dir)
            let fileline = s:GetLine(invpath, lineno)
            let quickfix_locations += [invpath.":".lineno.":".fileline]
        else
            echoerr "Invalid invocation: ".invocation
        endif
    endfor
    return quickfix_locations
endfunction

function! s:GetDefs(filepath, lineno, method_name, src_dir, build_dir)
    call s:Status("Searching for method definitions")

    let invoke_cmd = '/usr/bin/python '.g:jcall_py_path.'/invoke.py "'.a:filepath.'" '.a:lineno.' "'.a:method_name.'" "'.a:build_dir.'"'
    call s:Debug("Invoke: ".invoke_cmd)
    let output = split(system(invoke_cmd), '\n')
    if v:shell_error != 0
        for line in output
            echom line
        endfor
        echoerr "Command returned ".v:shell_error
    endif

    let quickfix_locations = []
    for location in output
        let line = split(location, ":", 1) " keepempty to support default package
        if len(line) == 3
            let [package, l:file, lineno] = line
            let invpath = s:GetPath(package, file, a:src_dir)
            let fileline = s:GetLine(invpath, lineno)
            let quickfix_locations += [invpath.":".lineno.":".fileline]
        else
            echoerr "Invalid invocation: ".location
        endif
    endfor
    return quickfix_locations
endfunction

function! s:PopulateQuickfix(quickfix_locations)
    let old_errorformat=&errorformat
    let &errorformat='%f:%l:%m'
    if (g:jcall_open == 1) && (len(a:quickfix_locations) > 1)
        copen " Open the Quickfix window
    endif
    if (g:jcall_open == 0) || (g:jcall_jump == 1)
        cexpr a:quickfix_locations
    else
        cgetexpr a:quickfix_locations " get means don't jump to the first one right away
    endif
    let &errorformat=old_errorformat
endfunction

function! s:GetDirs(filepath)
    let src_dir = expand('%:p:h')
    let build_dir = expand('%:p:h')
    for pair in g:jcall_src_build_pairs
        let src = pair[0]
        let build = pair[1]
        if stridx(a:filepath, src) == 0
            let src_dir = src
            let build_dir = build
        endif
    endfor
    call s:Debug("Setting build path to ".build_dir.".")
    call s:Debug("Setting source path to ".src_dir.".")
    return [src_dir, build_dir]
endfunction

function! s:Open(filepath, lineno)
    let [src_dir, build_dir] = s:GetDirs(a:filepath)

    try
        call s:Refresh(build_dir)
        let method_signature = s:GetMethodSignature(a:filepath, a:lineno, build_dir)
        let quickfix_locations = s:GetCalls(method_signature, src_dir, build_dir)

        if len(quickfix_locations) == 0
            echo "No calls found."
        else
            call s:PopulateQuickfix(quickfix_locations)
        endif
    catch /.*/
      echoerr v:exception." occurred in ".v:throwpoint
    endtry
endfunction

function! s:Jump(filepath, lineno, method_name)
    let [src_dir, build_dir] = s:GetDirs(a:filepath)

    try
        call s:Refresh(build_dir)
        let quickfix_locations = s:GetDefs(a:filepath, a:lineno, a:method_name, src_dir, build_dir)

        if len(quickfix_locations) == 0
            echo "No calls found."
        else
            call s:PopulateQuickfix(quickfix_locations)
        endif
    catch /.*/
      echoerr v:exception." occurred in ".v:throwpoint
    endtry
endfunction


function! s:Clear(filepath)
    let [src_dir, build_dir] = s:GetDirs(a:filepath)

    " Make sure we don't wipe out the file system
    if len(g:jcall_tmp_path) > 2
        call system("rm -rf ".g:jcall_tmp_path.build_dir)
    endif
endfunction

noremap <unique> <script> <Plug>JCallOpen  <SID>Open
noremap <SID>Open :call <SID>Open(expand('%:p'),line('.'))<CR>
noremenu <script> Plugin.JCall <SID>Open

noremap <unique> <script> <Plug>JCallJump  <SID>Jump
noremap <SID>Jump :call <SID>Jump(expand('%:p'),line('.'), expand('<cword>'))<CR>
noremenu <script> Plugin.JCallJump <SID>Jump

noremap <unique> <script> <Plug>JCallClear  <SID>Clear
noremap <SID>Clear :call <SID>Clear(expand('%:p'))<CR>
noremenu <script> Plugin.JCallClear <SID>Clear
