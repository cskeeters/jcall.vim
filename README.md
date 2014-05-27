# JCall

JCall is a plugin for vim.  It allows a user to navigate java code in two ways (inspired by eclipse).

* See from where a method might be called. (Call Hierarchy)
* Jump to a method's definition.  Like ctags, but smarter and a little bit slower.

## Installation

This plugin requires python 2.4+ and support in vim.  You can test your vim by seeing if the following command returns a 1.

    :echo has('python')

This plugin also requires find, sed, make, and the JDK (for javap).

See Vundle or Pathogen

## Usage

![Screencast of open](https://raw.githubusercontent.com/cskeeters/i/master/jcall.gif)
![Screencast of jump](https://raw.githubusercontent.com/cskeeters/i/master/jcall_jump.gif)

See the [vim help](doc/jcall.txt)

## Developer Info

This plugin is beta quality at the moment.  It works by calling javap for each compiled class file and parsing the results.  This is easier because the output of javap will have fully quantified method and class names and line breaks in consistent places.  It's possible that the regular expressions will need to be updated for future versions of javap.

## Testing

To checkout that the plugin is working, the [jcall_test](https://github.com/cskeeters/jcall_test) repository has some basic java code that can help verify correct functionality.

### Preliminary steps

1. Checkout jcall_test
2. Use ant to compile (has to have compiled code to work)
3. Install the plugin
4. [Configure mappings](doc/jcall.txt)
5. Configure project setting in `g:jcall_src_build_pairs`
6. Restart vim

## Test Cases:

1. Basic call hierarchy works.
  * Edit chad/Test.java
  * Move cursor to the body of doHi
  * Trigger JCall `,ch`
  * Should jump to the doHi call in main()
2. Basic jump works.
  * Move the cursor over doHi
  * `f3` to jump back to doHi
  * Should jump to the doHi definition
