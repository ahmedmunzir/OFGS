Name:           ofgs
%{!?upstream_version:%global upstream_version 2.2.1}
Version:        %{upstream_version}
Release:        1%{?dist}
Summary:        OpenFOAM graph generation and monitoring suite

License:        MIT
URL:            https://github.com/ahmedmunzir/OFGS
Source0:        %{url}/archive/refs/tags/v%{version}.tar.gz#/%{name}-%{version}.tar.gz

BuildArch:      noarch
BuildRequires:  bash
BuildRequires:  coreutils
BuildRequires:  make
BuildRequires:  python3 >= 3.9

Requires:       bash
Requires:       coreutils
# Fedora's gnuplot package includes the Qt terminal. On EL9 it is supplied by EPEL.
Requires:       gnuplot >= 5.4
Requires:       python3 >= 3.9
Requires:       sed

%description
OFGS discovers supported OpenFOAM post-processing datasets and generates
gnuplot dashboards and standalone graphs. It also provides live dashboard,
individual graph, and selected multi-graph monitoring modes.

%prep
%autosetup -n OFGS-%{version}

%build
# OFGS contains interpreted Bash and Python sources; there is nothing to build.

%install
%{__make} install PREFIX=%{_prefix} DESTDIR=%{buildroot}
install -Dpm 0644 docs/ofgs.1 %{buildroot}%{_mandir}/man1/ofgs.1

%check
python3 -B -m unittest discover -s tests -v

%files
%license LICENSE
%doc README.md
%{_bindir}/ofgs
%{_datadir}/ofgs/
%{_mandir}/man1/ofgs.1*

%changelog
* Mon Aug 10 2026 Munzir Ahmed <ahmedmunzir.ma@gmail.com> - 2.2.1-1
- Initial RPM package.
