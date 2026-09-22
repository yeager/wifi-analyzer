Name:           wifi-analyzer
Version:        0.1.18
Release:        1%{?dist}
Summary:        GTK application for inspecting nearby Wi-Fi networks
License:        GPL-3.0-or-later
URL:            https://github.com/yeager/wifi-analyzer
Source0:        %{name}-%{version}.tar.gz

BuildArch:       noarch
BuildRequires:   appstream
BuildRequires:   desktop-file-utils
BuildRequires:   gettext
BuildRequires:   gtk4
BuildRequires:   libadwaita
BuildRequires:   python3-devel
BuildRequires:   python3-pytest
BuildRequires:   python3dist(setuptools)
Requires:        NetworkManager
Requires:        iw
Requires:        libadwaita
Requires:        python3-cairo
Requires:        python3-gobject

%description
WiFi Analyzer displays nearby access points, their signal strength, channel,
security mode, overlap and regulatory hints through NetworkManager.

%prep
%autosetup

%build
python3 scripts/compile_translations.py
%pyproject_wheel

%install
%pyproject_install
install -Dpm0644 data/io.github.yeager.WifiAnalyzer.desktop \
  %{buildroot}%{_datadir}/applications/io.github.yeager.WifiAnalyzer.desktop
install -Dpm0644 data/io.github.yeager.WifiAnalyzer.metainfo.xml \
  %{buildroot}%{_metainfodir}/io.github.yeager.WifiAnalyzer.metainfo.xml
install -Dpm0644 docs/man/wifi-analyzer.1 \
  %{buildroot}%{_mandir}/man1/wifi-analyzer.1
install -Dpm0644 docs/man/sv/wifi-analyzer.1 \
  %{buildroot}%{_mandir}/sv/man1/wifi-analyzer.1
install -Dpm0644 data/icons/hicolor/256x256/apps/io.github.yeager.WifiAnalyzer.png \
  %{buildroot}%{_datadir}/icons/hicolor/256x256/apps/io.github.yeager.WifiAnalyzer.png
install -Dpm0644 data/icons/hicolor/512x512/apps/io.github.yeager.WifiAnalyzer.png \
  %{buildroot}%{_datadir}/icons/hicolor/512x512/apps/io.github.yeager.WifiAnalyzer.png
for mo in locale/*/LC_MESSAGES/wifi-analyzer.mo; do
  lang=$(basename $(dirname $(dirname "$mo")))
  install -Dpm0644 "$mo" %{buildroot}%{_datadir}/locale/$lang/LC_MESSAGES/wifi-analyzer.mo
done

%check
PYTHONPATH=src pytest -q

%files
%license LICENSE
%doc README.md
%{_bindir}/wifi-analyzer
%{python3_sitelib}/wifi_analyzer/
%{python3_sitelib}/wifi_analyzer-*.dist-info/
%{_datadir}/applications/io.github.yeager.WifiAnalyzer.desktop
%{_metainfodir}/io.github.yeager.WifiAnalyzer.metainfo.xml
%{_mandir}/man1/wifi-analyzer.1*
%{_mandir}/sv/man1/wifi-analyzer.1*
%{_datadir}/icons/hicolor/*/apps/io.github.yeager.WifiAnalyzer.png
%{_datadir}/locale/*/LC_MESSAGES/wifi-analyzer.mo

%changelog
* Tue Sep 22 2026 Daniel Nylander <po@danielnylander.se> - 0.1.18-1
- Fix direct launch with Python from the source directory.

* Mon Sep 21 2026 Daniel Nylander <po@danielnylander.se> - 0.1.17-1
- Add zoom and guidance to the interactive channel view.
