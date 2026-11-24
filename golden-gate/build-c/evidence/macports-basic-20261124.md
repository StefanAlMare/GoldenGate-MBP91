# Golden Gate C — MacPorts BASIC evidence, 24 November 2026

**Source:** operator-supplied MacPorts registry report from MacBookPro9,1 at 09:57:40 EET. The report is reproduced below, with all 173 numbered entries and the original 15-port BASIC check. The **BASIC (B)** label belongs to the report's package profile; the machine's macOS build is explicitly 26B131.

**Interpretation:** "INSTALAT" denotes an active registry entry. Source-only build provenance, dependency/requested classification and runtime testing of each individual port are **not** established by this report. [Concise English interpretation](../MACPORTS.md) · [Română](../MACPORTS.ro.md) · [Structured 173-row CSV](../ports.csv).

---

# GoldenGate — MacPorts BASIC (B)

- Data: 2026-11-24 09:57:40 EET
- Calculator: MacBookPro9,1
- macOS: 27.2.1
- Build: 26B131
- Arhitectura: x86_64
- MacPorts: Version: 2.12.7

## 1. Verificare profil BASIC

| Nr. | Port | Versiune | Status |
|---:|---|---|---|
| 1 | python314 | @3.14.10_0+lto+optimizations | INSTALAT |
| 2 | py314-pip | @26.2.2_0 | INSTALAT |
| 3 | git | @2.56.1_0+credential_osxkeychain+diff_highlight+doc+pcre+perl5_34 | INSTALAT |
| 4 | curl | @8.23.0_1+brotli+http2+idn+psl+ssl+zstd | INSTALAT |
| 5 | wget | @1.25.0_1+gnutls | INSTALAT |
| 6 | rsync | @3.5.1_0 | INSTALAT |
| 7 | jq | @1.8.2_0 | INSTALAT |
| 8 | htop | @3.5.3_0 | INSTALAT |
| 9 | tree | @2.3.2_0 | INSTALAT |
| 10 | coreutils | @9.12_0 | INSTALAT |
| 11 | xz | @5.8.4_0 | INSTALAT |
| 12 | zstd | @1.5.7_0 | INSTALAT |
| 13 | 7zip | @26.06_0 | INSTALAT |
| 14 | smartmontools | @7.5_0+attributelog+savestates | INSTALAT |
| 15 | iperf3 | @3.22.1_0 | INSTALAT |

### Rezultat BASIC: 15 / 15 instalate

## 2. Verificare ICU

- ICU: INSTALAT — @78.3_1

## 3. Inventar complet MacPorts

```text
001. 7zip                           @26.06_0
002. autoconf                       @2.73_0
003. automake                       @1.20_0
004. bison                          @3.8.2_2
005. bison-runtime                  @3.8.2_0
006. brotli                         @1.2.1_0
007. bzip2                          @1.0.8_1
008. cairo                          @1.18.6_0+quartz+x11
009. cmake-bootstrap                @3.9.6_0
010. coreutils                      @9.12_0
011. curl                           @8.23.0_1+brotli+http2+idn+psl+ssl+zstd
012. curl-ca-bundle                 @8.23.0_1
013. db48                           @4.8.30_5
014. dbus                           @1.16.4_2
015. expat                          @2.10.0_0
016. flex                           @2.7.3_0
017. fontconfig                     @2.18.3_0
018. freetype                       @2.15.0_0
019. gdbm                           @1.26_0
020. gettext                        @1.0_0
021. gettext-runtime                @1.0_0
022. gettext-tools-libs             @1.0_0
023. git                            @2.56.1_0+credential_osxkeychain+diff_highlight+doc+pcre+perl5_34
024. glib2                          @2.88.3_2+dbus+x11
025. glib2-bootstrap                @2.88.3_2+dbus+x11
026. gmp                            @6.3.0_0
027. gnutls                         @3.8.14_0
028. gobject-introspection          @1.86.0_1
029. gobject-introspection-bootstrap @1.86.0_1
030. gperf                          @3.3_0
031. gsettings-desktop-schemas      @50.0_1
032. help2man                       @1.49.3_2+perl5_34
033. htop                           @3.5.3_0
034. icu                            @78.3_1
035. iperf3                         @3.22.1_0
036. jq                             @1.8.2_0
037. kerberos5                      @1.22.3_0
038. libcomerr                      @1.47.4_0
039. libedit                        @20260512-3.1_0
040. libelf                         @0.8.13_6
041. libffi                         @3.6.0_0
042. libiconv                       @1.19_0
043. libidn2                        @2.3.8_0
044. libpixman                      @0.46.4_0
045. libpng                         @1.6.59_0
046. libproxy                       @0.5.12_0
047. libpsl                         @0.23.3_0
048. libtasn1                       @4.21.0_0
049. libtextstyle                   @1.0_0
050. libtool                        @2.6.2_1
051. libunistring                   @1.5_0
052. libxml2                        @2.15.4_0
053. libxslt                        @1.1.45_0
054. lmdb                           @1.0.3_1
055. lz4                            @1.11.1_0
056. lzip                           @1.26_0
057. lzo2                           @2.10_0
058. m4                             @1.4.21_0
059. meson                          @1.12.1_0
060. mpdecimal                      @4.0.1_0
061. ncurses                        @6.6_0
062. nettle                         @3.10.2_0
063. nghttp2                        @1.71.0_0
064. ninja                          @1.13.2_1
065. oniguruma6                     @6.9.10_0
066. openssl                        @3_33
067. openssl3                       @3.6.5_0
068. p5.34-authen-sasl              @2.210.0_0
069. p5.34-b-cow                    @0.7.0_0
070. p5.34-cgi                      @5.20.0_0
071. p5.34-clone                    @0.510.0_0
072. p5.34-compress-raw-bzip2       @2.225.0_0
073. p5.34-compress-raw-zlib        @2.226.0_0
074. p5.34-crypt-urandom            @0.550.0_0
075. p5.34-data-dumper              @2.183.0_0
076. p5.34-devel-hide               @0.1.600_0
077. p5.34-digest-hmac              @1.50.0_0
078. p5.34-digest-sha1              @2.130.0_4
079. p5.34-encode                   @3.250.0_0
080. p5.34-encode-din66003          @0.50.0_0
081. p5.34-encode-eucjpascii        @0.30.0_1
082. p5.34-encode-hanextra          @0.230.0_6
083. p5.34-encode-iso2022           @0.40.0_0
084. p5.34-encode-jisx0213          @0.40.0_0
085. p5.34-encode-locale            @1.50.0_0
086. p5.34-error                    @0.170.310_0
087. p5.34-gssapi                   @0.280.0_3
088. p5.34-html-parser              @3.870.0_0
089. p5.34-html-tagset              @3.240.0_0
090. p5.34-http-date                @6.80.0_0
091. p5.34-http-message             @7.40.0_0
092. p5.34-io-compress              @2.225.0_0
093. p5.34-io-html                  @1.4.0_0
094. p5.34-io-socket-ssl            @2.99.0_0
095. p5.34-locale-gettext           @1.70.0_1
096. p5.34-locale-maketext-simple   @0.210.0_3
097. p5.34-lwp-mediatypes           @6.50.0_0
098. p5.34-mime-base32              @1.303.0_0
099. p5.34-mime-base64              @3.160.0_0
100. p5.34-mime-charset             @1.013.1_0
101. p5.34-module-load              @0.360.0_0
102. p5.34-module-load-conditional  @0.740.0_0
103. p5.34-net-smtp-ssl             @1.40.0_0
104. p5.34-net-ssleay               @1.960.0_0
105. p5.34-params-check             @0.380.0_1
106. p5.34-pod-escapes              @1.70.0_0
107. p5.34-pod-simple               @3.480.0_0
108. p5.34-pod2-base                @0.43.0_0
109. p5.34-regexp-ipv6              @0.30.0_0
110. p5.34-scalar-list-utils        @1.700.0_0
111. p5.34-sub-uplevel              @0.280.0_0
112. p5.34-term-readkey             @2.380.0_0
113. p5.34-term-size-any            @0.2.0_0
114. p5.34-term-size-perl           @0.31.0_0
115. p5.34-term-table               @0.28.0_0
116. p5.34-test-exception           @0.430.0_0
117. p5.34-test-nowarnings          @1.60.0_0
118. p5.34-test-pod                 @1.520.0_0
119. p5.34-test-simple              @1.302.226_0
120. p5.34-test-warn                @0.370.0_0
121. p5.34-time-hires               @1.976.400_0
122. p5.34-time-local               @1.350.0_0
123. p5.34-timedate                 @2.350.0_0
124. p5.34-unicode-linebreak        @2019.1.0_1
125. p5.34-uri                      @5.400.0_0
126. p5.34-version                  @0.993.400_0
127. p5.34-xsloader                 @0.240.0_0
128. p11-kit                        @0.26.6_0
129. pcre2                          @10.49_0
130. perl5.34                       @5.34.3_1
131. pip_select                     @0.1_3
132. pkgconfig                      @0.29.2_0
133. popt                           @1.19_0
134. py314-build                    @1.6.0_0
135. py314-installer                @1.1.0_0
136. py314-mako                     @1.3.12_0
137. py314-markdown                 @3.10.3_0
138. py314-markupsafe               @3.0.4_0
139. py314-meson                    @1.12.1_0
140. py314-packaging                @26.3_0
141. py314-pip                      @26.2.2_0
142. py314-pyproject_hooks          @1.3.3_0
143. py314-setuptools               @84.2.1_0
144. py314-wheel                    @0.48.0_0
145. python3_select                 @0.1_0
146. python3_select-314             @0.1_1
147. python314                      @3.14.10_0+lto+optimizations
148. python_select                  @0.3_10
149. python_select-314              @0.3_1
150. re2c                           @4.6_0
151. readline                       @8.3.006_0
152. rsync                          @3.5.1_0
153. smartmontools                  @7.5_0+attributelog+savestates
154. sqlite3                        @3.54.1_1
155. texinfo                        @7.3_0+perl5_34
156. tree                           @2.3.2_0
157. wget                           @1.25.0_1+gnutls
158. xorg-libX11                    @1.8.12_0
159. xorg-libXau                    @1.0.12_0
160. xorg-libxcb                    @1.17.0_0+python314
161. xorg-libXdmcp                  @1.1.5_0
162. xorg-libXext                   @1.3.6_0
163. xorg-util-macros               @1.20.2_0
164. xorg-xcb-proto                 @1.17.0_0+python314
165. xorg-xcb-util                  @0.4.1_0
166. xorg-xorgproto                 @2024.1_0
167. xorg-xtrans                    @1.5.2_0
168. xrender                        @0.9.12_0
169. xxhashlib                      @0.8.4_0
170. xz                             @5.8.4_0
171. xz-bootstrap                   @5.8.4_1
172. zlib                           @1.4_0
173. zstd                           @1.5.7_0

TOTAL PORTURI ACTIVE: 173
```

## 4. Observatii

- Inventar citit direct din registrul MacPorts.
- INSTALAT inseamna versiune activa.
- Inventarul nu certifica separat provenienta din sursa.
- Testarea functionala a fiecarui port este distincta.
