
# List the sources
set(module_name "getpmatelk")
set(fortran_src_file "${CMAKE_CURRENT_SOURCE_DIR}/getpmatelk.f90")

set(generated_module_file ${module_name}${TRIQS_PYTHON_MODULE_EXT})

add_custom_target(${module_name} ALL
  DEPENDS ${generated_module_file}
  )

# for Intel fortran compilers we manually have to link against libiomp5 (-fqopenmp is always on in f2py)
if(CMAKE_Fortran_COMPILER_ID MATCHES "Intel")
  set(F2PY_INTEL_OPTIONS -liomp5 --fcompiler=intelem)
endif()

##generate the fortran python wrapper shared library
add_custom_command(
  OUTPUT ${generated_module_file}
  COMMAND ${TRIQS_PYTHON_EXECUTABLE} -m numpy.f2py --build-dir ${CMAKE_CURRENT_BINARY_DIR}/meson --f90exec=${CMAKE_Fortran_COMPILER} --f77exec=${CMAKE_Fortran_COMPILER} ${F2PY_INTEL_OPTIONS} -c ${fortran_src_file} -m ${module_name} > elk_f2py.log
  WORKING_DIRECTORY ${CMAKE_CURRENT_BINARY_DIR}
  )

# where to install
install(DIRECTORY ${CMAKE_CURRENT_BINARY_DIR} DESTINATION
${TRIQS_PYTHON_LIB_DEST_ROOT}/${PROJECT_NAME}/converters/elktools FILES_MATCHING PATTERN "*.so"
PERMISSIONS OWNER_READ OWNER_WRITE OWNER_EXECUTE GROUP_READ GROUP_EXECUTE
WORLD_READ WORLD_EXECUTE PATTERN "CMakeFiles" EXCLUDE)

# user warning
message(STATUS "-----------------------------------------------------------------------------")
message(STATUS "                             ********  USER NOTE ******** ")
message(STATUS "  This version of DFTTools contains interface routines to read Elk's binary  ")
message(STATUS "  files. ")
message(STATUS "-----------------------------------------------------------------------------")

