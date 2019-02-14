/*
 *  File :     config.h
 *
 *
 *  Author :   Francesco Prelz ($Author: mezzadri $)
 *  e-mail :   "francesco.prelz@mi.infn.it"
 *
 *  Revision history :
 *  23-Nov-2007 Original release
 *
 *  Description:
 *    Prototypes of functions defined in config.c
 *
 *  Copyright (c) Members of the EGEE Collaboration. 2007-2010. 
 *
 *    See http://www.eu-egee.org/partners/ for details on the copyright
 *    holders.  
 *  
 *    Licensed under the Apache License, Version 2.0 (the "License"); 
 *    you may not use this file except in compliance with the License. 
 *    You may obtain a copy of the License at 
 *  
 *        http://www.apache.org/licenses/LICENSE-2.0 
 *  
 *    Unless required by applicable law or agreed to in writing, software 
 *    distributed under the License is distributed on an "AS IS" BASIS, 
 *    WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. 
 *    See the License for the specific language governing permissions and 
 *    limitations under the License.
 */

#ifndef __CONFIG_H__
#define __CONFIG_H__

#include <stdio.h>

typedef struct config_entry_s
 {
   char *key;
   char *value;
   char **values;
   int n_values;
   struct config_entry_s *next;
 } config_entry;

typedef struct config_handle_s
 {
   char *install_path;
   char *bin_path;
   char *config_path;
   config_entry *list;
 } config_handle;

config_handle *config_read(const char *path);
config_entry *config_get(const char *key, config_handle *handle);
int config_test_boolean(const config_entry *entry);
void config_free(config_handle *handle);

#define CONFIG_FILE_BASE "batch_gahp.config"

#define CONFIG_SKIP_WHITESPACE_FWD(c) while ((*(c) == ' ')  || (*(c) == '\t') || \
                                  (*(c) == '\n') || (*(c) == '\r') ) (c)++;
#define CONFIG_SKIP_WHITESPACE_BCK(c) while ((*(c) == ' ')  || (*(c) == '\t') || \
                                  (*(c) == '\n') || (*(c) == '\r') ) (c)--;

#ifndef TRUE
#define TRUE 1
#endif
#ifndef FALSE
#define FALSE 0
#endif

#endif /*defined __CONFIG_H__*/
