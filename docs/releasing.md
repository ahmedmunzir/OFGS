# Package releases

OFGS package releases use tags in the exact form `vMAJOR.MINOR.PATCH`, such as
`v2.3.0`. A valid tag builds `ofgs_2.3.0-1_all.deb` and
`ofgs-2.3.0-1.el9.noarch.rpm`, tests both installed packages, and attaches them
and a SHA-256 checksum file to the matching GitHub Release.

The workflow can be run manually to exercise its build and installation tests;
manual runs never publish a release. EL9 users must enable EPEL because it
supplies GNUPlot. This workflow publishes GitHub Release artifacts only; APT
and DNF repositories are not provided yet.
