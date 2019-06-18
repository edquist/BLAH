#
#       Copyright (c) 2004 on behalf of the EU EGEE Project:
#       The European Organization for Nuclear Research (CERN),
#       Istituto Nazionale di Fisica Nucleare (INFN), Italy
#       Datamat Spa, Italy
#       Centre National de la Recherche Scientifique (CNRS), France
#       CS Systeme d'Information (CSSI), France
#       Royal Institute of Technology, Center for Parallel Computers (KTH-PDC), Sweden
#       Universiteit van Amsterdam (UvA), Netherlands
#       University of Helsinki (UH.HIP), Finland
#       University of Bergen (UiB), Norway
#       Council for the Central Laboratory of the Research Councils (CCLRC), United Kingdom
#
#       Authors: Francesco Prelz <francesco.prelz@mi.infn.it>
#       Version info: $Id: configure.ac,v 1.46.2.13 2012/03/09 08:32:06 pandreet Exp $
#       Release: $Name: glite-ce-blahp_R_1_16_5_1 $
#

AC_PREREQ(2.57)
AC_INIT([GLite CE blahp], [1.16.5])
AC_CONFIG_AUX_DIR([./project])
AM_INIT_AUTOMAKE([1.6.3 subdir-objects])
AC_CONFIG_SRCDIR([src/main.c])
                                                                                
#Environment.
WORKDIR=`pwd`
AC_SUBST(WORKDIR)
                                                                                                                          
dnl Checks for programs.
AC_PROG_AWK
AC_PROG_CC
AM_PROG_CC_C_O
AC_PROG_CXX
AC_PROG_LIBTOOL

dnl Checks for libraries.
dnl Replace `main' with a function in -lpthread:
AC_CHECK_LIB(pthread, main)

dnl Checks for header files.
AC_HEADER_STDC
AC_HEADER_SYS_WAIT
AC_CHECK_HEADERS(sys/time.h syslog.h)

dnl Checks for typedefs, structures, and compiler characteristics.
AC_C_CONST
AC_TYPE_PID_T
AC_HEADER_TIME

dnl Checks for library functions.
AC_CHECK_FUNCS(select socket strdup strerror bsearch vsnprintf)

GLITE_CHECK_LIBDIR
GLITE_CHECK_INITDIR

AC_ARG_WITH(dist_location,
   [  --with-dist-location=PFX     prefix where DIST location is. (pwd)],
   [],
   with_dist_location=$WORKDIR/../dist)

DISTTAR=$with_dist_location

AC_SUBST(DISTTAR)

AC_CLASSADS([], AC_MSG_RESULT(["CLASSADS ok"]), AC_MSG_ERROR(["CLASSADS not found"]))

have_globus=no
AC_GLOBUS([], have_globus=yes, have_globus=no)
AC_MSG_RESULT(["GLOBUS found $have_globus"])
AM_CONDITIONAL([HAVE_GLOBUS], [test x$have_globus = xyes])

dnl Temporarily built with no optimisation

CXXFLAGS="-g -O0"
CFLAGS="-g -O0"

AC_DEFINE(BLAHPD_BINDIR,"@bindir@")

# Configuration items
AC_PREFIX_DEFAULT([/opt/glite])
AC_CONFIG_FILES([Makefile])
AC_CONFIG_FILES([config/Makefile])
AC_CONFIG_FILES([src/Makefile])
AC_CONFIG_FILES([src/scripts/Makefile])

AC_OUTPUT
