pulltpenxml - a utility for assembling an XML file from T-PEN projects
====

This is a library that talks to the T-PEN server, given user account
credentials, and pulls down a set of projects to assemble them into
a single manuscript. The manuscript is then parsed with the (https://github.com/DHUniWien/tpen2tei)[tpen2tei] utility into an XML file.

Your own username/password, and possibly your own server URLs, should
go into the configuration file `tpen.yml`.

Example usage
---

	./pull M1768 > ms_1768.xml

...will pull down all projects accessible to the provided user account,
assemble them (in alphabetical order by title) into a single manuscript
description, and create an XML file from the result.
